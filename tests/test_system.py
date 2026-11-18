"""End-to-end system tests for The AI Archive.

They run against the live stack (see the `tests` service in
docker-compose.yaml) and use the real Firebase project: each run registers two
throwaway users through Firebase's REST API and deletes them afterwards.

Run:
    docker compose up -d
    docker compose --profile test run --rm tests
"""
import os
import re
import time
import unittest
import uuid

import requests

BASE_URL = os.getenv("BASE_URL", "http://localhost:8000").rstrip("/")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://prometheus:9090").rstrip("/")
CONFIG_FILE = os.getenv("FIREBASE_CONFIG_FILE", "/config/firebase-config.js")

POLL_TIMEOUT = 90          # seconds to wait for one command to complete
STARTUP_TIMEOUT = 180      # seconds to wait for the API to become healthy
WORD_LIMIT = 45

IDENTITY = "https://identitytoolkit.googleapis.com/v1/accounts"

_users = []


def firebase_api_key():
    key = os.getenv("FIREBASE_API_KEY")

    if key:
        return key

    with open(CONFIG_FILE, encoding="utf-8") as handle:
        match = re.search(r'apiKey:\s*"([^"]+)"', handle.read())

    if not match:
        raise RuntimeError("No apiKey found in " + CONFIG_FILE)

    return match.group(1)


class User:
    """A throwaway Firebase user."""

    def __init__(self):
        self.email = f"systemtest-{uuid.uuid4().hex[:12]}@example.com"
        password = "Sys-" + uuid.uuid4().hex[:12]
        reply = requests.post(
            f"{IDENTITY}:signUp?key={firebase_api_key()}",
            json={
                "email": self.email,
                "password": password,
                "returnSecureToken": True
            },
            timeout=30
        )

        if reply.status_code != 200:
            raise RuntimeError(
                "Could not register a test user: " + reply.text[:300]
            )

        data = reply.json()
        self.token = data["idToken"]
        self.uid = data["localId"]
        _users.append(self)

    @property
    def headers(self):
        return {"Authorization": "Bearer " + self.token}

    def delete(self):
        requests.post(
            f"{IDENTITY}:delete?key={firebase_api_key()}",
            json={"idToken": self.token},
            timeout=30
        )


def tearDownModule():
    for user in _users:
        try:
            user.delete()
        except Exception as error:
            print("Could not delete test user:", error)


def wait_for_api():
    deadline = time.time() + STARTUP_TIMEOUT

    while time.time() < deadline:
        try:
            if requests.get(BASE_URL + "/health", timeout=5).ok:
                return
        except requests.RequestException:
            pass

        time.sleep(3)

    raise RuntimeError("The API did not become healthy in time")


def api(method, path, user=None, **kwargs):
    headers = dict(kwargs.pop("headers", {}))

    if user is not None:
        headers.update(user.headers)

    return requests.request(
        method, BASE_URL + path, headers=headers, timeout=30, **kwargs
    )


def new_game(user):
    reply = api("POST", "/api/v1/games", user)
    assert reply.status_code == 200, reply.text
    return reply.json()["game_id"]


def submit(user, gid, text, request_id=None):
    body = {"text": text}

    if request_id:
        body["request_id"] = request_id

    return api("POST", f"/api/v1/games/{gid}/actions", user, json=body)


def wait_for_completion(user, rid):
    deadline = time.time() + POLL_TIMEOUT
    last = {}

    while time.time() < deadline:
        reply = api("GET", f"/api/v1/requests/{rid}", user)
        assert reply.status_code == 200, reply.text
        last = reply.json()

        if last["status"] == "COMPLETED":
            return last

        time.sleep(0.5)

    raise AssertionError("Request never completed, last state: " + str(last))


def run_command(user, gid, text):
    reply = submit(user, gid, text)
    assert reply.status_code == 200, reply.text
    return wait_for_completion(user, reply.json()["request_id"])


class SystemTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        wait_for_api()
        cls.alice = User()
        cls.bob = User()

    # ------------------------------------------------------------------
    # Health and access control
    # ------------------------------------------------------------------
    def test_01_health(self):
        reply = api("GET", "/health")
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()["status"], "healthy")

    def test_02_anonymous_requests_are_rejected(self):
        for method, path in (
            ("POST", "/api/v1/games"),
            ("GET", "/api/v1/costs"),
            ("POST", "/api/v1/carbon/sci"),
            ("GET", "/api/v1/authentication/me"),
        ):
            with self.subTest(route=method + " " + path):
                self.assertEqual(api(method, path).status_code, 401)

    def test_03_invalid_token_is_rejected(self):
        reply = api(
            "GET",
            "/api/v1/authentication/me",
            headers={"Authorization": "Bearer not-a-real-token"}
        )
        self.assertEqual(reply.status_code, 401)

    def test_04_me_returns_the_firebase_identity(self):
        reply = api("GET", "/api/v1/authentication/me", self.alice)
        self.assertEqual(reply.status_code, 200)
        self.assertEqual(reply.json()["uid"], self.alice.uid)

    # ------------------------------------------------------------------
    # Games
    # ------------------------------------------------------------------
    def test_10_new_game_starts_in_reception(self):
        reply = api("POST", "/api/v1/games", self.alice)
        self.assertEqual(reply.status_code, 200)
        game = reply.json()
        self.assertEqual(game["location"], "reception")
        self.assertEqual(game["status"], "IN_PROGRESS")
        self.assertEqual(game["inventory"], [])
        self.assertEqual(game["room"]["items"], ["access_card"])

        again = api("GET", "/api/v1/games/" + game["game_id"], self.alice)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(again.json()["game_id"], game["game_id"])

    def test_11_users_cannot_see_each_others_games(self):
        gid = new_game(self.alice)
        self.assertEqual(
            api("GET", "/api/v1/games/" + gid, self.bob).status_code, 404
        )

        done = run_command(self.alice, gid, "look around")
        self.assertEqual(
            api("GET", "/api/v1/requests/" + done["request_id"], self.bob)
            .status_code,
            404
        )
        self.assertEqual(
            submit(self.bob, gid, "look around").status_code, 404
        )

    def test_12_empty_command_is_rejected(self):
        gid = new_game(self.alice)
        self.assertEqual(submit(self.alice, gid, "").status_code, 422)

    # ------------------------------------------------------------------
    # The full asynchronous pipeline
    # ------------------------------------------------------------------
    def test_20_first_command_goes_through_the_whole_pipeline(self):
        gid = new_game(self.alice)
        submitted = submit(self.alice, gid, "take the access card")
        self.assertEqual(submitted.status_code, 200)
        self.assertEqual(submitted.json()["status"], "PENDING")

        done = wait_for_completion(self.alice, submitted.json()["request_id"])

        self.assertEqual(done["semantic_result"]["action"], "TAKE_ITEM")
        self.assertEqual(
            done["semantic_result"]["entities"], {"item": "access_card"}
        )
        self.assertTrue(done["game_result"]["success"])
        self.assertEqual(done["game_state"]["inventory"], ["access_card"])
        self.assertTrue(done["ai_response"]["message"].strip())
        self.assertLessEqual(
            len(done["ai_response"]["message"].split()), WORD_LIMIT
        )

    def test_21_hint_returns_a_short_guide_message(self):
        gid = new_game(self.alice)
        done = run_command(self.alice, gid, "give me a hint")
        self.assertEqual(done["semantic_result"]["action"], "ASK_FOR_HINT")
        self.assertTrue(done["game_result"]["success"])
        message = done["ai_response"]["message"]
        self.assertTrue(message.strip())
        self.assertLessEqual(len(message.split()), WORD_LIMIT)

    def test_22_failed_actions_still_complete(self):
        gid = new_game(self.alice)
        done = run_command(self.alice, gid, "go north")
        self.assertEqual(done["semantic_result"]["action"], "MOVE")
        self.assertFalse(done["game_result"]["success"])
        self.assertEqual(done["game_state"]["location"], "reception")
        self.assertTrue(done["ai_response"]["message"].strip())

    def test_23_nonsense_completes_without_breaking_the_game(self):
        gid = new_game(self.alice)
        done = run_command(self.alice, gid, "zxqv blorp wibble")
        self.assertIn("game_result", done)
        self.assertEqual(done["game_state"]["location"], "reception")

    def test_24_repeated_request_id_runs_once(self):
        gid = new_game(self.alice)
        rid = "same-" + uuid.uuid4().hex[:10]

        first = submit(self.alice, gid, "look around", rid).json()
        second = submit(self.alice, gid, "look around", rid).json()
        self.assertEqual(first["request_id"], second["request_id"])

        wait_for_completion(self.alice, rid)
        game = api("GET", "/api/v1/games/" + gid, self.alice).json()
        self.assertEqual(game["turn"], 1)

    def test_25_pending_requests_hide_the_game_state(self):
        gid = new_game(self.alice)
        pending = submit(self.alice, gid, "look around").json()
        self.assertEqual(pending["status"], "PENDING")
        self.assertNotIn("game_state", pending)
        wait_for_completion(self.alice, pending["request_id"])

    def test_30_complete_playthrough_reaches_the_exit(self):
        gid = new_game(self.alice)
        steps = (
            ("take the access card", "TAKE_ITEM"),
            ("use the access card", "USE_ITEM"),
            ("go north", "MOVE"),
            ("take fragment 1", "TAKE_ITEM"),
            ("go east", "MOVE"),
            ("take fragment 2", "TAKE_ITEM"),
            ("take fragment 3", "TAKE_ITEM"),
            ("go north", "MOVE"),
        )
        done = {}

        for text, expected_action in steps:
            with self.subTest(command=text):
                done = run_command(self.alice, gid, text)
                self.assertEqual(
                    done["semantic_result"]["action"],
                    expected_action,
                    done["semantic_result"]
                )
                self.assertTrue(
                    done["game_result"]["success"], done["game_result"]
                )

        self.assertEqual(done["game_state"]["status"], "WON")
        self.assertEqual(done["game_state"]["location"], "exit")

        final = api("GET", "/api/v1/games/" + gid, self.alice).json()
        self.assertEqual(final["status"], "WON")
        self.assertEqual(final["turn"], len(steps))
        self.assertEqual(len(final["inventory"]), 4)

    # ------------------------------------------------------------------
    # Cost and carbon endpoints
    # ------------------------------------------------------------------
    def test_40_cost_records(self):
        reply = api("GET", "/api/v1/costs", self.alice)
        self.assertEqual(reply.status_code, 200)
        names = [row["service_name"] for row in reply.json()]
        self.assertGreaterEqual(len(names), 10)
        self.assertEqual(names, sorted(names))

    def test_41_cost_calculation(self):
        reply = api(
            "POST",
            "/api/v1/costs/calculate",
            self.alice,
            json={
                "services": ["api", "redis"],
                "hours": 2,
                "instances": {"api": 2}
            }
        )
        self.assertEqual(reply.status_code, 200)
        self.assertAlmostEqual(reply.json()["total"], 0.16, places=6)

    def test_42_cost_record_lifecycle(self):
        name = "systest-" + uuid.uuid4().hex[:8]
        created = api(
            "POST",
            "/api/v1/costs",
            self.alice,
            json={"service_name": name, "cost_per_hour": 1.5}
        )
        self.assertEqual(created.status_code, 201)
        record_id = created.json()["id"]

        duplicate = api(
            "POST",
            "/api/v1/costs",
            self.alice,
            json={"service_name": name, "cost_per_hour": 1}
        )
        self.assertEqual(duplicate.status_code, 409)

        updated = api(
            "PUT",
            f"/api/v1/costs/{record_id}",
            self.alice,
            json={"cost_per_hour": 2.5}
        )
        self.assertEqual(updated.json()["cost_per_hour"], 2.5)

        self.assertEqual(
            api("DELETE", f"/api/v1/costs/{record_id}", self.alice).status_code,
            200
        )
        self.assertEqual(
            api("DELETE", f"/api/v1/costs/{record_id}", self.alice).status_code,
            404
        )

    def test_43_sci_calculation(self):
        reply = api("POST", "/api/v1/carbon/sci", self.alice, json={})
        self.assertEqual(reply.status_code, 200)
        body = reply.json()
        self.assertAlmostEqual(body["sci_gco2e_per_unit"], 0.05718, places=6)
        self.assertEqual(body["functional_unit_name"], "request")

        custom = api(
            "POST",
            "/api/v1/carbon/sci",
            self.alice,
            json={"services": ["api", "ollama"], "functional_units": 500}
        )
        self.assertAlmostEqual(
            custom.json()["sci_gco2e_per_unit"], 0.0561, places=6
        )

    def test_44_carbon_input_is_validated(self):
        self.assertEqual(
            api("POST", "/api/v1/carbon/sci", self.alice,
                json={"functional_units": 0}).status_code,
            422
        )
        self.assertEqual(
            api("POST", "/api/v1/carbon/sci", self.alice,
                json={"services": ["nope"]}).status_code,
            404
        )

    # ------------------------------------------------------------------
    # Monitoring and security headers (run after the playthrough)
    # ------------------------------------------------------------------
    def test_50_security_headers(self):
        reply = api("GET", "/health")
        self.assertEqual(reply.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(reply.headers["X-Frame-Options"], "DENY")

    def test_51_metrics_show_the_game_activity(self):
        text = api("GET", "/metrics").text
        self.assertIn("http_requests_total", text)
        self.assertIn("game_actions_total", text)
        self.assertIn("narratives_total", text)

    def test_52_prometheus_is_scraping_the_api(self):
        deadline = time.time() + 60
        state = None

        while time.time() < deadline:
            try:
                targets = requests.get(
                    PROMETHEUS_URL + "/api/v1/targets", timeout=10
                ).json()["data"]["activeTargets"]
                state = {
                    t["labels"]["job"]: t["health"] for t in targets
                }

                if state.get("api") == "up":
                    return
            except requests.RequestException:
                pass

            time.sleep(3)

        self.fail("Prometheus is not scraping the API: " + str(state))


if __name__ == "__main__":
    unittest.main(verbosity=2)
