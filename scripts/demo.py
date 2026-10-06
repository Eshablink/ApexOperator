from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi.testclient import TestClient

from apexoperator.api.main import create_app


def main() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        workspace = root / "workspace"
        workspace.mkdir()

        # Reuse the committed deterministic demo fixture.
        source = Path("workspace/incoming_batch.json")
        (workspace / "incoming_batch.json").write_text(
            source.read_text(encoding="utf-8"),
            encoding="utf-8",
        )

        client = TestClient(
            create_app(
                workspace_dir=workspace,
                database_path=root / "apexoperator.sqlite3",
            )
        )

        clerk = {"Authorization": "Bearer dev-clerk-token"}
        manager = {"Authorization": "Bearer dev-manager-token"}

        low = client.post(
            "/tasks",
            headers=clerk,
            json={"invoice_id": "INV-LOW-001"},
        ).json()

        high = client.post(
            "/tasks",
            headers=clerk,
            json={
                "invoice_id": "INV-HIGH-001",
                "justification": "Threshold exceeded",
            },
        ).json()

        approved = client.post(
            f"/tasks/{high['task_id']}/approve",
            headers=manager,
            json={"comment": "Verified by finance manager"},
        ).json()

        audit = client.get("/audit/verify", headers=manager).json()

        print("ApexOperator demo")
        print(f"Low invoice:      {low['status']}")
        print(f"High invoice:     {high['status']}")
        print(f"After approval:   {approved['status']}")
        print(f"Audit integrity:  {audit['integrity_valid']}")


if __name__ == "__main__":
    main()
