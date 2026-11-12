"""
Load test for ServiceDesk-AI (Locust).

Simulates requesters and agents using the seeded demo accounts, so start the app with demo
data first (for example `sh scripts/e2e_server.sh`, which serves on port 8765), then:

    pip install -r loadtests/requirements.txt
    locust -f loadtests/locustfile.py --host http://127.0.0.1:8765

Open http://localhost:8089 to set the number of users, or run headless:

    locust -f loadtests/locustfile.py --host http://127.0.0.1:8765 \
        --headless --users 50 --spawn-rate 10 --run-time 1m

Notes
- POST /triage/suggest is rate limited per user (30 per minute by default), so a 429 there is
  the expected, healthy behaviour and is not counted as a failure.
- Logins use the seeded demo passwords, which only exist on demo databases.
"""
import random

from locust import HttpUser, between, task

REQUESTER = {"email": "requester@example.com", "password": "RequesterPassword123!"}
AGENT = {"email": "agent@example.com", "password": "AgentPassword123!"}

TRIAGE_TEXTS = [
    ("VPN keeps disconnecting", "The corporate VPN drops every few minutes when working from home."),
    ("Laptop will not boot", "Screen stays black after the logo and the fan runs at full speed."),
    ("Cannot access shared drive", "Access denied when opening the finance folder since this morning."),
    ("Outlook not syncing", "New emails do not arrive until I restart the application."),
]


class SignedInUser(HttpUser):
    abstract = True
    wait_time = between(1, 3)
    credentials: dict = {}

    def on_start(self):
        res = self.client.post("/api/v1/auth/login", json=self.credentials, name="/auth/login")
        res.raise_for_status()
        self.client.headers["Authorization"] = f"Bearer {res.json()['access_token']}"
        self.ticket_ids: list[int] = []

    def _remember_tickets(self):
        res = self.client.get("/api/v1/tickets?page_size=20", name="/tickets (list)")
        if res.ok:
            self.ticket_ids = [t["id"] for t in res.json()["items"]]

    @task(5)
    def list_tickets(self):
        self._remember_tickets()

    @task(3)
    def view_ticket(self):
        if not self.ticket_ids:
            self._remember_tickets()
        if self.ticket_ids:
            ticket_id = random.choice(self.ticket_ids)
            self.client.get(f"/api/v1/tickets/{ticket_id}", name="/tickets/{id}")
            self.client.get(f"/api/v1/tickets/{ticket_id}/comments", name="/tickets/{id}/comments")

    @task(2)
    def triage_suggestion(self):
        title, description = random.choice(TRIAGE_TEXTS)
        with self.client.post(
            "/api/v1/triage/suggest",
            json={"title": title, "description": description},
            name="/triage/suggest",
            catch_response=True,
        ) as res:
            if res.status_code == 429:
                res.success()  # the per-user rate limit doing its job

    @task(1)
    def create_ticket(self):
        title, description = random.choice(TRIAGE_TEXTS)
        self.client.post(
            "/api/v1/tickets",
            json={"title": f"[load] {title}", "description": description, "category": "other"},
            name="/tickets (create)",
        )


class Requester(SignedInUser):
    weight = 4
    credentials = REQUESTER


class Agent(SignedInUser):
    weight = 1
    credentials = AGENT

    @task(2)
    def view_reports(self):
        self.client.get("/api/v1/reports/overdue", name="/reports/overdue")
        self.client.get("/api/v1/reports/agent-workload", name="/reports/agent-workload")
