import plistlib
import unittest

import pjkit


class TestParseTime(unittest.TestCase):
    def test_parses_hh_mm(self):
        self.assertEqual(pjkit.parse_time("09:00"), (9, 0))

    def test_parses_single_digits_and_surrounding_space(self):
        self.assertEqual(pjkit.parse_time(" 9:5 "), (9, 5))

    def test_parses_end_of_day(self):
        self.assertEqual(pjkit.parse_time("23:59"), (23, 59))

    def test_rejects_hour_out_of_range(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_time("24:00")

    def test_rejects_minute_out_of_range(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_time("10:60")

    def test_rejects_non_numeric(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_time("noon")

    def test_rejects_missing_colon(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_time("0900")


class TestParseEvery(unittest.TestCase):
    def test_minutes(self):
        self.assertEqual(pjkit.parse_every("30m"), 1800)

    def test_hours(self):
        self.assertEqual(pjkit.parse_every("2h"), 7200)

    def test_seconds(self):
        self.assertEqual(pjkit.parse_every("90s"), 90)

    def test_case_insensitive_unit_and_space(self):
        self.assertEqual(pjkit.parse_every(" 15M "), 900)

    def test_rejects_zero(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_every("0m")

    def test_rejects_missing_unit(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_every("30")

    def test_rejects_garbage(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_every("soon")


class TestParseDays(unittest.TestCase):
    def test_maps_weekday_names_to_launchd_ints(self):
        self.assertEqual(pjkit.parse_days("mon,wed,fri"), [1, 3, 5])

    def test_sunday_is_zero(self):
        self.assertEqual(pjkit.parse_days("sun"), [0])

    def test_saturday_is_six(self):
        self.assertEqual(pjkit.parse_days("sat"), [6])

    def test_case_insensitive_and_spaces(self):
        self.assertEqual(pjkit.parse_days(" Mon , TUE "), [1, 2])

    def test_dedupes_and_sorts(self):
        self.assertEqual(pjkit.parse_days("fri,mon,fri"), [1, 5])

    def test_rejects_unknown_day(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_days("funday")


class TestValidateName(unittest.TestCase):
    def test_accepts_simple(self):
        self.assertEqual(pjkit.validate_name("triage"), "triage")

    def test_accepts_dash_underscore_digits(self):
        self.assertEqual(pjkit.validate_name("daily-triage_2"), "daily-triage_2")

    def test_rejects_bad_names(self):
        for bad in ["my job", "no/slash", "dot.dot", "", "UPPER"]:
            with self.assertRaises(pjkit.JobSpecError):
                pjkit.validate_name(bad)


class TestScheduleToLaunchd(unittest.TestCase):
    def test_single_daily_time_is_a_dict(self):
        keys = pjkit.schedule_to_launchd(
            {"kind": "calendar", "times": ["09:00"], "days": [], "run_at_load": False}
        )
        self.assertEqual(keys, {"StartCalendarInterval": {"Hour": 9, "Minute": 0}})

    def test_multiple_times_is_a_list(self):
        keys = pjkit.schedule_to_launchd(
            {"kind": "calendar", "times": ["09:00", "18:30"], "days": []}
        )
        self.assertEqual(
            keys["StartCalendarInterval"],
            [{"Hour": 9, "Minute": 0}, {"Hour": 18, "Minute": 30}],
        )

    def test_weekdays_cartesian_with_times(self):
        keys = pjkit.schedule_to_launchd(
            {"kind": "calendar", "times": ["09:00"], "days": ["mon", "fri"]}
        )
        self.assertEqual(
            keys["StartCalendarInterval"],
            [
                {"Weekday": 1, "Hour": 9, "Minute": 0},
                {"Weekday": 5, "Hour": 9, "Minute": 0},
            ],
        )

    def test_interval(self):
        keys = pjkit.schedule_to_launchd({"kind": "interval", "every": "30m"})
        self.assertEqual(keys, {"StartInterval": 1800})

    def test_run_at_load_added(self):
        keys = pjkit.schedule_to_launchd(
            {"kind": "interval", "every": "1h", "run_at_load": True}
        )
        self.assertEqual(keys, {"RunAtLoad": True, "StartInterval": 3600})

    def test_calendar_requires_a_time(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.schedule_to_launchd({"kind": "calendar", "times": [], "days": []})

    def test_rejects_unknown_kind(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.schedule_to_launchd({"kind": "weekly"})


class TestLabelAndPaths(unittest.TestCase):
    def test_label(self):
        self.assertEqual(pjkit.build_label("triage"), "com.dimitrov.pj.triage")

    def test_job_paths(self):
        p = pjkit.job_paths("/root/jobs", "triage")
        self.assertEqual(str(p.dir), "/root/jobs/triage")
        self.assertEqual(str(p.toml), "/root/jobs/triage/job.toml")
        self.assertEqual(str(p.wrapper), "/root/jobs/triage/wrapper.sh")
        self.assertEqual(
            str(p.plist), "/root/jobs/triage/com.dimitrov.pj.triage.plist"
        )
        self.assertEqual(str(p.log_out), "/root/jobs/triage/logs/out.log")
        self.assertEqual(str(p.log_err), "/root/jobs/triage/logs/err.log")

    def test_launch_agent_link(self):
        link = pjkit.launch_agent_link("/home/u/Library/LaunchAgents", "triage")
        self.assertEqual(
            str(link),
            "/home/u/Library/LaunchAgents/com.dimitrov.pj.triage.plist",
        )


class TestRenderWrapper(unittest.TestCase):
    def test_includes_shebang_cd_and_command(self):
        w = pjkit.render_wrapper("/my/repo", 'claude -p "hi"')
        self.assertTrue(w.startswith("#!/bin/zsh"))
        self.assertIn("cd /my/repo", w)
        self.assertIn('claude -p "hi"', w)

    def test_quotes_dir_with_spaces(self):
        w = pjkit.render_wrapper("/my repo", "echo hi")
        self.assertIn("cd '/my repo'", w)

    def test_captures_exit_without_zsh_reserved_status(self):
        # zsh's $status is a read-only alias for $?; assigning to it breaks the run.
        w = pjkit.render_wrapper("/tmp", "true")
        self.assertNotIn("status=", w)
        self.assertIn("rc=$?", w)
        self.assertIn("exit $rc", w)


class TestRenderPlist(unittest.TestCase):
    def test_round_trips_and_has_expected_keys(self):
        keys = {"StartInterval": 1800}
        xml = pjkit.render_plist(
            "com.x.y",
            "/jobs/y/wrapper.sh",
            keys,
            "/jobs/y/logs/out.log",
            "/jobs/y/logs/err.log",
        )
        data = plistlib.loads(xml.encode())
        self.assertEqual(data["Label"], "com.x.y")
        self.assertEqual(
            data["ProgramArguments"],
            ["/bin/zsh", "-i", "-c", "source /jobs/y/wrapper.sh"],
        )
        self.assertEqual(data["StartInterval"], 1800)
        self.assertEqual(data["StandardOutPath"], "/jobs/y/logs/out.log")
        self.assertEqual(data["StandardErrorPath"], "/jobs/y/logs/err.log")

    def test_carries_generated_comment(self):
        xml = pjkit.render_plist("com.x.y", "/w", {"StartInterval": 60}, "/o", "/e")
        self.assertIn("generated by pj", xml)


class TestTomlRoundTrip(unittest.TestCase):
    def test_round_trip_with_tricky_strings(self):
        data = {
            "name": "triage",
            "description": 'has "quotes" and \\ backslash',
            "working_dir": "/my/repo",
            "command": 'claude -p "say hi" --permission-mode dontAsk',
            "enabled": True,
            "schedule": {
                "kind": "calendar",
                "times": ["09:00", "18:30"],
                "days": ["mon", "fri"],
                "run_at_load": False,
            },
        }
        text = pjkit.dump_toml(data)
        self.assertEqual(pjkit.load_toml(text), data)

    def test_round_trip_interval(self):
        data = {
            "name": "poll",
            "enabled": False,
            "schedule": {"kind": "interval", "every": "30m", "run_at_load": True},
        }
        self.assertEqual(pjkit.load_toml(pjkit.dump_toml(data)), data)


class TestParseAtToken(unittest.TestCase):
    def test_time_only(self):
        self.assertEqual(pjkit.parse_at_token("09:00"), (None, "09:00"))

    def test_normalizes_time(self):
        self.assertEqual(pjkit.parse_at_token("9:5"), (None, "09:05"))

    def test_days_and_time(self):
        self.assertEqual(
            pjkit.parse_at_token("mon,fri 18:00"), (["mon", "fri"], "18:00")
        )

    def test_rejects_days_without_time(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_at_token("mon,fri")

    def test_rejects_bad_day(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.parse_at_token("funday 09:00")


class TestNormalizeDays(unittest.TestCase):
    def test_sorts_and_dedupes(self):
        self.assertEqual(pjkit.normalize_days("fri,mon,fri"), ["mon", "fri"])

    def test_accepts_list(self):
        self.assertEqual(pjkit.normalize_days(["sat", "sun"]), ["sun", "sat"])

    def test_rejects_unknown(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.normalize_days("xyz")


class TestBuildCalendarSchedule(unittest.TestCase):
    def test_times_only(self):
        self.assertEqual(
            pjkit.build_calendar_schedule(["09:00", "18:30"]),
            {
                "kind": "calendar",
                "times": ["09:00", "18:30"],
                "days": [],
                "run_at_load": False,
            },
        )

    def test_with_days_flag(self):
        self.assertEqual(
            pjkit.build_calendar_schedule(["09:00"], days="mon,fri")["days"],
            ["mon", "fri"],
        )

    def test_embedded_days(self):
        s = pjkit.build_calendar_schedule(["mon,fri 18:00"])
        self.assertEqual(s["days"], ["mon", "fri"])
        self.assertEqual(s["times"], ["18:00"])

    def test_dedupes_times(self):
        self.assertEqual(
            pjkit.build_calendar_schedule(["09:00", "09:00"])["times"], ["09:00"]
        )

    def test_conflict_embedded_and_flag(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.build_calendar_schedule(["mon 09:00"], days="fri")

    def test_inconsistent_embedded_days(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.build_calendar_schedule(["mon 09:00", "fri 18:00"])

    def test_partial_embedded_days(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.build_calendar_schedule(["mon 09:00", "18:00"])

    def test_requires_a_time(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.build_calendar_schedule([])

    def test_run_at_load(self):
        self.assertTrue(
            pjkit.build_calendar_schedule(["09:00"], run_at_load=True)["run_at_load"]
        )


class TestBuildIntervalSchedule(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(
            pjkit.build_interval_schedule("30m"),
            {"kind": "interval", "every": "30m", "run_at_load": False},
        )

    def test_validates(self):
        with self.assertRaises(pjkit.JobSpecError):
            pjkit.build_interval_schedule("nope")

    def test_run_at_load(self):
        self.assertTrue(pjkit.build_interval_schedule("1h", run_at_load=True)["run_at_load"])


class TestHumanSchedule(unittest.TestCase):
    def test_interval(self):
        self.assertEqual(
            pjkit.human_schedule({"kind": "interval", "every": "30m"}), "every 30m"
        )

    def test_daily_single_time(self):
        self.assertEqual(
            pjkit.human_schedule({"kind": "calendar", "times": ["09:00"], "days": []}),
            "daily at 09:00",
        )

    def test_daily_multiple_times(self):
        self.assertEqual(
            pjkit.human_schedule(
                {"kind": "calendar", "times": ["09:00", "18:30"], "days": []}
            ),
            "daily at 09:00, 18:30",
        )

    def test_weekdays(self):
        self.assertEqual(
            pjkit.human_schedule(
                {"kind": "calendar", "times": ["18:00"], "days": ["mon", "fri"]}
            ),
            "mon,fri at 18:00",
        )

    def test_run_at_load_suffix(self):
        self.assertEqual(
            pjkit.human_schedule(
                {"kind": "interval", "every": "1h", "run_at_load": True}
            ),
            "every 1h (+at load)",
        )


if __name__ == "__main__":
    unittest.main()
