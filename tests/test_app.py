"""Route and persistence tests. Run with: python -m unittest discover -s tests"""
import tempfile
import unittest
from pathlib import Path

import app as site_app


class AttendanceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db_path = Path(self.tmp.name) / "attendance.db"
        self.old_path = site_app.app.config["DATABASE_PATH"]
        site_app.app.config["DATABASE_PATH"] = str(self.db_path)
        site_app.app.config["TESTING"] = True
        site_app.init_db()
        self.client = site_app.app.test_client()
        self.client.get("/")
        with self.client.session_transaction() as sess:
            self.csrf = sess["csrf"]

    def tearDown(self):
        site_app.app.config["DATABASE_PATH"] = self.old_path
        self.tmp.cleanup()

    def post(self, date, count):
        return self.client.post("/api/attendance", json={"date": date, "count": count}, headers={"X-CSRF-Token": self.csrf})

    def put(self, rid, date, count, **extra):
        return self.client.put(f"/api/attendance/{rid}", json={"date": date, "count": count, **extra}, headers={"X-CSRF-Token": self.csrf})

    def test_create_existing_load_update_duplicate_and_validation(self):
        self.assertEqual(self.post("2026-10-01", 20).status_code, 200)
        self.assertEqual(self.client.get("/api/attendance/by-date/2026-10-01").json["record"]["labour_count"], 20)
        self.assertEqual(self.post("2026-10-01", 25).status_code, 409)
        record_id = self.client.get("/api/attendance/by-date/2026-10-01").json["record"]["id"]
        self.assertEqual(self.put(record_id, "2026-10-01", 25).status_code, 200)
        self.assertEqual(self.post("2026-10-02", -1).status_code, 400)
        self.assertEqual(self.post("2026-10-02", "").status_code, 400)
        self.assertEqual(self.post("not-a-date", 3).status_code, 400)
        self.assertEqual(self.post("2026-10-02", 1.5).status_code, 400)

    def test_move_occupied_date_requires_explicit_replacement_and_preserves_creation(self):
        self.post("2026-10-01", 20)
        self.post("2026-10-02", 25)
        rows = self.client.get("/api/attendance?month=2026-10").json["all"]
        src = next(r for r in rows if r["attendance_date"] == "2026-10-01")
        target = next(r for r in rows if r["attendance_date"] == "2026-10-02")
        self.assertEqual(self.put(src["id"], "2026-10-02", 18).status_code, 409)
        self.assertEqual(self.put(src["id"], "2026-10-02", 18, replace_id=target["id"]).status_code, 200)
        month = self.client.get("/api/attendance?month=2026-10").json
        self.assertEqual((month["total"], month["days"]), (18, 1))
        moved = month["month"][0]
        self.assertEqual(moved["id"], src["id"])
        self.assertEqual(moved["created_at"], src["created_at"])

    def test_recent_month_delete_csrf_and_persistence(self):
        for day, count in [("01", 20), ("02", 25), ("03", 18), ("04", 10), ("05", 5), ("06", 2)]:
            self.post(f"2026-10-{day}", count)
        listing = self.client.get("/api/attendance?month=2026-10").json
        self.assertEqual(len(listing["recent"]), 5)
        self.assertEqual((listing["total"], listing["days"]), (80, 6))
        rid = listing["all"][0]["id"]
        self.assertEqual(self.client.delete(f"/api/attendance/{rid}").status_code, 400)
        deleted = self.client.delete(f"/api/attendance/{rid}", headers={"X-CSRF-Token": self.csrf})
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(self.client.get("/api/attendance?month=2026-10").json["days"], 5)
        site_app.init_db()  # Startup schema check does not replace saved rows.
        self.assertEqual(self.client.get("/api/attendance?month=2026-10").json["days"], 5)


if __name__ == "__main__":
    unittest.main()
