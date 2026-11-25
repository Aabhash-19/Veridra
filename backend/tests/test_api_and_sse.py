import asyncio
import json

import httpx
import pytest

from app.main import app


@pytest.mark.asyncio
async def test_api_projects_runs_artifacts_export_and_sse() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        # Health
        health = await client.get("/health")
        assert health.status_code == 200
        assert health.json()["status"] == "ok"

        # Integrations never leak keys
        integ = await client.get("/api/v1/settings/integrations")
        assert integ.status_code == 200
        assert integ.json()["llm_configured"] is False
        assert "GEMINI_API_KEY" not in json.dumps(integ.json())
        model_ids = [m["id"] for m in integ.json()["available_models"]]
        assert "gpt-4o-mini" in model_ids
        assert "openai/gpt-oss-120b" in model_ids
        assert "gemini-3.6-flash" in model_ids
        assert "gemini-3.5-flash" in model_ids

        # Missing keys without demo flag returns PROVIDER_NOT_CONFIGURED
        bad_run = await client.post(
            "/api/v1/runs",
            json={"topic": "ICPC problem solving habits", "platform": "linkedin"},
        )
        assert bad_run.status_code == 422
        assert bad_run.json()["error"]["code"] == "PROVIDER_NOT_CONFIGURED"

        # Create project
        proj_resp = await client.post(
            "/api/v1/projects",
            json={"name": "CS Education", "defaults": {"platform": "linkedin", "depth": "deep"}},
        )
        assert proj_resp.status_code == 201
        project_id = proj_resp.json()["project_id"]

        # Create run in explicit Demo Mode
        run_resp = await client.post(
            "/api/v1/runs",
            json={
                "topic": "How ICPC develops algorithmic problem-solving skills",
                "platform": "linkedin",
                "project_id": project_id,
                "use_demo_mode": True,
            },
        )
        assert run_resp.status_code == 201
        run_data = run_resp.json()
        run_id = run_data["run_id"]
        assert run_data["execution_mode"] == "demo"

        # Poll briefly until background worker finishes
        detail_json = {}
        for _ in range(40):
            det = await client.get(f"/api/v1/runs/{run_id}")
            assert det.status_code == 200
            detail_json = det.json()
            if detail_json["status"] in {"completed", "completed_with_warnings", "failed"}:
                break
            await asyncio.sleep(0.05)

        assert detail_json["status"] == "completed"
        assert detail_json["latest_artifact"] is not None
        approved_art_id = detail_json["latest_artifact"]["artifact_id"]
        approved_ver = detail_json["latest_artifact"]["version"]

        # SSE stream replays ordered events and terminates
        sse_resp = await client.get(f"/api/v1/runs/{run_id}/events")
        assert sse_resp.status_code == 200
        lines = sse_resp.text.splitlines()
        data_lines = [ln[6:] for ln in lines if ln.startswith("data: ")]
        assert len(data_lines) >= 4
        sequences = [json.loads(dl)["sequence"] for dl in data_lines]
        assert sequences == sorted(sequences)
        assert json.loads(data_lines[-1])["event_type"] == "run.completed"

        # Replay with after_sequence skips older events
        replay_resp = await client.get(
            f"/api/v1/runs/{run_id}/events?after_sequence={sequences[-2]}"
        )
        replay_data = [
            json.loads(ln[6:]) for ln in replay_resp.text.splitlines() if ln.startswith("data: ")
        ]
        assert len(replay_data) == 1
        assert replay_data[0]["sequence"] == sequences[-1]

        # Cancel on completed run returns cancellation_accepted=False and does NOT mislabel
        cancel_done = await client.post(f"/api/v1/runs/{run_id}/cancel")
        assert cancel_done.status_code == 200
        assert cancel_done.json()["cancellation_accepted"] is False
        assert cancel_done.json()["status"] == "completed"

        # User edit creates NEW immutable version
        edit_resp = await client.put(
            f"/api/v1/artifacts/{approved_art_id}",
            json={
                "title": "Edited ICPC Title",
                "body_markdown": "User edited post content.\n\n[1] https://icpc.global/worldfinals/rules",
                "expected_parent_version_id": approved_art_id,
            },
        )
        assert edit_resp.status_code == 200
        edited_json = edit_resp.json()
        assert edited_json["version"] == approved_ver + 1
        assert edited_json["parent_version_id"] == approved_art_id
        assert edited_json["differs_from_agent_approved"] is True

        # Export Markdown and Plain Text
        md_exp = await client.get(
            f"/api/v1/artifacts/{edited_json['artifact_id']}/export?format=md"
        )
        assert md_exp.status_code == 200
        assert "Edited ICPC Title" in md_exp.text
        assert "https://icpc.global/worldfinals/rules" in md_exp.text

        txt_exp = await client.get(
            f"/api/v1/artifacts/{edited_json['artifact_id']}/export?format=txt"
        )
        assert txt_exp.status_code == 200
        assert "User edited post content." in txt_exp.text

        # Retry creates child attempt while keeping original intact
        retry_resp = await client.post(f"/api/v1/runs/{run_id}/retry")
        assert retry_resp.status_code == 201
        assert retry_resp.json()["parent_run_id"] == run_id

        # Wait briefly for retry child run cleanup
        child_id = retry_resp.json()["run_id"]
        for _ in range(40):
            cd = await client.get(f"/api/v1/runs/{child_id}")
            if cd.json()["status"] in {"completed", "completed_with_warnings", "failed"}:
                break
            await asyncio.sleep(0.05)


@pytest.mark.asyncio
async def test_api_benchmark_single_vs_multi_agent() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
        ds = await client.get("/api/v1/benchmarks/dataset")
        assert ds.status_code == 200
        assert len(ds.json()) == 30

        bmk_resp = await client.post(
            "/api/v1/benchmarks",
            json={
                "name": "CI Paired Comparison",
                "topic_count": 2,
                "include_holdout": False,
                "strategies": ["single_agent", "multi_agent"],
                "repeats": 1,
                "model_override": "gemini-3.5-flash",
                "use_demo_mode": True,
            },
        )
        assert bmk_resp.status_code == 201
        bmk_id = bmk_resp.json()["benchmark_id"]

        bmk_detail = {}
        for _ in range(60):
            res = await client.get(f"/api/v1/benchmarks/{bmk_id}")
            bmk_detail = res.json()
            if bmk_detail["status"] == "completed":
                break
            await asyncio.sleep(0.05)

        assert bmk_detail["status"] == "completed"
        assert bmk_detail["config"]["model_override"] == "gemini-3.5-flash"
        assert len(bmk_detail["condition_summaries"]) == 2
        assert len(bmk_detail["cases"]) == 4

        first_case_id = bmk_detail["cases"][0]["case_id"]
        rate_resp = await client.post(
            f"/api/v1/benchmarks/{bmk_id}/cases/{first_case_id}/rating",
            json={"rating": 4.5, "notes": "Clear and accurate."},
        )
        assert rate_resp.status_code == 200
        assert rate_resp.json()["human_rating"] == 4.5
