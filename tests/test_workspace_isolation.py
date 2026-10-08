from fastapi.testclient import TestClient

from apexoperator.api.main import create_app
from apexoperator.security.auth import InMemoryAuthenticator, Principal
from apexoperator.security.rbac import Role


def make_client(tmp_path):
    auth = InMemoryAuthenticator({
        "clerk-a": Principal("clerk-a", Role.AP_CLERK, "org-a"),
        "manager-a": Principal("manager-a", Role.FINANCE_MANAGER, "org-a"),
        "clerk-b": Principal("clerk-b", Role.AP_CLERK, "org-b"),
    })
    client = TestClient(create_app(database_path=tmp_path / "app.sqlite3", authenticator=auth))
    client.app.state.service.task_store.create(
        "task-a",
        "org-a",
        "INV-SHARED-001",
        "PENDING_HUMAN_APPROVAL",
        "clerk-a",
        "HUMAN_ESCALATION_REQUIRED",
        None,
    )
    return client


def test_clerk_can_only_read_own_workspace_task(tmp_path):
    client = make_client(tmp_path)

    own = client.get("/tasks/task-a", headers={"Authorization": "Bearer clerk-a"})
    assert own.status_code == 200
    assert own.json()["requested_by"] == "clerk-a"

    cross_workspace = client.get("/tasks/task-a", headers={"Authorization": "Bearer clerk-b"})
    assert cross_workspace.status_code == 404

    dashboard = client.get("/dashboard/data", headers={"Authorization": "Bearer clerk-b"})
    assert dashboard.status_code == 403


def test_manager_sees_workspace_tasks_but_not_other_workspace_tasks(tmp_path):
    client = make_client(tmp_path)
    other = client.app.state.service.task_store
    other.create(
        "task-b",
        "org-b",
        "INV-SHARED-001",
        "AUTO_APPROVED",
        "clerk-b",
        "AUTO_APPROVED",
        None,
    )

    dashboard = client.get("/dashboard/data", headers={"Authorization": "Bearer manager-a"})
    assert dashboard.status_code == 200
    task_ids = {item["task_id"] for item in dashboard.json()["tasks"]}
    assert task_ids == {"task-a"}

    cross_workspace = client.get("/tasks/task-b", headers={"Authorization": "Bearer manager-a"})
    assert cross_workspace.status_code == 404


def test_same_invoice_id_can_exist_in_different_workspaces(tmp_path):
    client = make_client(tmp_path)
    client.app.state.service.task_store.create(
        "task-b",
        "org-b",
        "INV-SHARED-001",
        "AUTO_APPROVED",
        "clerk-b",
        "AUTO_APPROVED",
        None,
    )
    assert client.app.state.service.task_store.get_by_invoice_id("INV-SHARED-001", "org-a")["task_id"] == "task-a"
    assert client.app.state.service.task_store.get_by_invoice_id("INV-SHARED-001", "org-b")["task_id"] == "task-b"
