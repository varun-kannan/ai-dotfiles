"""Decision engine math, learning and outcome labelling. Each test has its own logs."""
import json
import os
import time

from helpers import ROOT, Sandbox

from engine import decide, outcomes, session

NEVER = lambda: 0.99      # exploration never fires
ALWAYS = lambda: 0.0      # exploration always fires


def iso(ts):
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(ts)) + ".000Z"


class Core(Sandbox):
    def test_flag_true_false_unsure(self):
        self.assertIs(decide.decide("is_project", {"code_files": 1}, log=False)["answer"], True)
        self.assertIs(decide.decide("is_project", {}, log=False)["answer"], False)
        # z = -2.2 + 3.6 * (1/3) + 0.9 = -0.1, p = 0.475: inside [0.35, 0.5)
        d = decide.decide("pointer_useful", {"new_specific": 1 / 3, "first_prompt": 1}, log=False, rng=NEVER)
        self.assertIsNone(d["answer"])
        self.assertAlmostEqual(d["p"], 0.475, places=2)

    def test_explore_acts_only_on_unsure(self):
        unsure = {"new_specific": 1 / 3, "first_prompt": 1}
        d = decide.decide("pointer_useful", unsure, log=False, rng=ALWAYS)
        self.assertIs(d["answer"], True)
        self.assertTrue(d["explored"])
        low = decide.decide("pointer_useful", {"new_specific": 1 / 3}, log=False, rng=ALWAYS)
        self.assertIs(low["answer"], False)
        self.assertFalse(low["explored"])
        self.assertIs(decide.decide("is_project", {"code_files": 0.6}, log=False, rng=ALWAYS)["answer"], None,
                      "a question without explore never explores")

    def test_reasons_sorted_and_limited(self):
        d = decide.decide("is_project", {"code_files": 0.5, "has_src": 1, "session_trigger": 1, "unknown": 9}, log=False)
        self.assertEqual([k for k, _ in d["reasons"]], ["code_files", "has_src", "session_trigger"],
                         "largest first; a signal with no weight is not a reason")
        cfg = decide.config()
        cfg["is_project"]["weights"]["extra"] = 0.1
        real, decide.config = decide.config, lambda: cfg
        try:
            d = decide.decide("is_project", {"code_files": 0.5, "has_src": 1, "session_trigger": 1, "extra": 1}, log=False)
        finally:
            decide.config = real
        self.assertEqual(len(d["reasons"]), 3, "at most three")
        self.assertNotIn("extra", [k for k, _ in d["reasons"]])
        self.assertEqual([abs(v) for _, v in d["reasons"]], sorted([abs(v) for _, v in d["reasons"]], reverse=True))

    def test_unknown_question_raises(self):
        with self.assertRaises(KeyError):
            decide.decide("nope", {}, log=False)

    def test_extreme_signals_do_not_overflow(self):
        self.assertEqual(decide.decide("is_project", {"code_files": 1e9}, log=False)["p"], 1.0)
        self.assertLess(decide.decide("is_project", {"code_files": -1e9}, log=False)["p"], 1e-6)

    def test_logging_on_and_off(self):
        decide.decide("is_project", {"code_files": 1}, log=False)
        self.assertFalse((self.shared / "logs" / "decisions.jsonl").exists())
        d = decide.decide("is_project", {"code_files": 1}, ctx={"root": "/x"})
        rows = decide.read_log("decisions")
        self.assertEqual([(r["id"], r["ctx"], r["signals"]) for r in rows], [(d["id"], {"root": "/x"}, {"code_files": 1})])


class Calibration(Sandbox):
    def test_needs_enough_outcomes_then_blends(self):
        thin = {"q": {"8": {"n": decide.MIN_BIN_COUNT - 1, "hits": 0}}}
        self.assertEqual(decide.calibrate("q", 0.85, thin), 0.85)
        table = {"q": {"8": {"n": 100, "hits": 20}}}
        self.assertAlmostEqual(decide.calibrate("q", 0.85, table), (20 + 10 * 0.85) / 110, places=6)
        self.assertEqual(decide.calibrate("q", 0.15, table), 0.15)
        self.assertAlmostEqual(decide.calibrate("q", 1.0, {"q": {"9": {"n": 100, "hits": 100}}}), 1.0, places=6)

    def test_calibration_file_changes_the_answer(self):
        self.write_json(self.shared / "data" / "calibration.json", {"pointer_useful": {"8": {"n": 200, "hits": 0}}})
        sig = {"new_specific": 1.0}      # raw p = sigmoid(1.4) = 0.80
        d = decide.decide("pointer_useful", sig, log=False, rng=NEVER)
        self.assertAlmostEqual(d["p_raw"], 0.802, places=2)
        self.assertLess(d["p"], 0.1)
        self.assertIs(d["answer"], False)


class Weights(Sandbox):
    def test_learned_weights_merge_over_config(self):
        self.write_json(self.shared / "data" / "weights.json",
                        {"pointer_useful": {"bias": -1.0, "weights": {"new_specific": 2.0, "gone_signal": 9}},
                         "is_project": {"bias": 99, "weights": {}}, "not_a_question": {"bias": 1, "weights": {}}})
        q = decide.questions()
        self.assertEqual(q["pointer_useful"]["bias"], -1.0)
        self.assertEqual(q["pointer_useful"]["weights"]["new_specific"], 2.0)
        self.assertNotIn("gone_signal", q["pointer_useful"]["weights"])
        self.assertEqual(q["pointer_useful"]["weights"]["first_prompt"], decide.config()["pointer_useful"]["weights"]["first_prompt"])
        self.assertEqual(q["is_project"]["bias"], 99, "merge applies to any flag present in the file")

    def test_bad_weights_file_is_ignored(self):
        (self.shared / "data").mkdir(parents=True)
        (self.shared / "data" / "weights.json").write_text("[1, 2]")
        self.assertEqual(decide.questions()["pointer_useful"]["bias"], decide.config()["pointer_useful"]["bias"])


class Learn(Sandbox):
    def feed(self, n, rule):
        for i in range(n):
            sig = {"new_specific": 1.0, "first_prompt": 0, "short_prompt": i % 2}
            d = decide.decide("pointer_useful", sig, rng=NEVER)
            decide.record_outcome(d["id"], rule(sig))

    def test_refit_moves_weights_toward_outcomes_within_bounds(self):
        self.feed(120, lambda s: s["short_prompt"] == 0)
        changes = decide.learn()
        self.assertTrue(any(c.startswith("pointer_useful: weights refit") for c in changes), changes)
        learned = json.loads((self.shared / "data" / "weights.json").read_text())["pointer_useful"]
        base = decide.config()["pointer_useful"]
        self.assertLess(learned["weights"]["short_prompt"], base["weights"]["short_prompt"])
        for k, w in learned["weights"].items():
            self.assertLessEqual(abs(w - base["weights"][k]), decide.MAX_WEIGHT_SHIFT + 1e-9)
        self.assertLessEqual(abs(learned["bias"] - base["bias"]), decide.MAX_WEIGHT_SHIFT + 1e-9)
        self.assertIn("weights refit", (self.shared / "logs" / "learn.log").read_text())
        table = json.loads((self.shared / "data" / "calibration.json").read_text())["pointer_useful"]
        self.assertEqual(sum(b["n"] for b in table.values()), 120)
        self.assertEqual(sum(b["hits"] for b in table.values()), 60)

    def test_too_few_outcomes_means_no_refit(self):
        self.feed(decide.MIN_LABELS_TO_FIT - 1, lambda s: s["short_prompt"] == 0)
        self.assertFalse(any("refit" in c for c in decide.learn()))
        self.assertEqual(json.loads((self.shared / "data" / "weights.json").read_text()), {})

    def test_questions_not_marked_learn_are_left_alone(self):
        for i in range(100):
            d = decide.decide("is_project", {"code_files": 1})
            decide.record_outcome(d["id"], False)
        decide.learn()
        self.assertNotIn("is_project", json.loads((self.shared / "data" / "weights.json").read_text()))
        self.assertNotIn("is_project", json.loads((self.shared / "data" / "calibration.json").read_text()))

    def test_first_outcome_wins(self):
        d = decide.decide("pointer_useful", {"new_specific": 1.0}, rng=NEVER)
        decide.record_outcome(d["id"], True)
        decide.record_outcome(d["id"], False)
        self.assertTrue(decide.labelled()["pointer_useful"][0]["hit"])

    def test_evaluate_counts(self):
        a = decide.decide("pointer_useful", {"new_specific": 1.0}, rng=NEVER)
        decide.decide("pointer_useful", {"new_specific": 1 / 3, "first_prompt": 1}, rng=NEVER)
        decide.decide("pointer_useful", {"new_specific": 1 / 3, "first_prompt": 1}, rng=ALWAYS)
        decide.decide("pointer_useful", {}, rng=NEVER)
        decide.record_outcome(a["id"], True)
        r = decide.evaluate()["pointer_useful"]
        self.assertEqual((r["decisions"], r["acted"], r["explored"], r["unsure"], r["labelled"]), (4, 2, 1, 2, 1),
                         "an explored answer was an unsure one")
        self.assertEqual(r["hit_rate_of_labelled"], 1.0)
        self.assertAlmostEqual(r["calibration_error_of_labelled"], round(1 - a["p"], 3), places=3)

    def test_rotation_keeps_all_rows_and_skips_bad_lines(self):
        old_limit = decide.LOG_LIMIT
        decide.LOG_LIMIT = 1200
        try:
            ids = [decide.decide("is_project", {"code_files": 1})["id"] for _ in range(12)]
        finally:
            decide.LOG_LIMIT = old_limit
        with open(self.shared / "logs" / "decisions.jsonl", "a") as fh:
            fh.write("not json\n123\n{\"no\": \"id\"}\n")
        self.assertEqual([r["id"] for r in decide.read_log("decisions")], ids)
        self.assertGreater(len([f for f in os.listdir(self.shared / "logs") if f.startswith("decisions.jsonl.")]), 0)


class Outcomes(Sandbox):
    def transcript(self, entries):
        path = self.tmp / "t.jsonl"
        path.write_text("\n".join(json.dumps(e) for e in entries) + "\n")
        return str(path)

    def user(self, ts, text="do the thing"):
        return {"timestamp": iso(ts), "message": {"role": "user", "content": text}}

    def reply(self, ts, model="claude-opus-5-5", tools=(), sidechain=False):
        content = [{"type": "tool_use", "name": n, "input": i} for n, i in tools]
        return {"timestamp": iso(ts), "isSidechain": sidechain, "message": {"role": "assistant", "model": model, "content": content}}

    def decision(self, q, ts, ctx):
        signals = {"new_specific": 1.0} if q == "pointer_useful" else {"gap": 1.0}
        d = decide.decide(q, signals, ctx=ctx, rng=NEVER)
        self.assertIs(d["answer"], True)
        path = self.shared / "logs" / "decisions.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines()]
        rows[-1]["ts"] = int(ts)
        path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        return d["id"]

    def hit_of(self, did):
        for rows in decide.labelled().values():
            for r in rows:
                if r["id"] == did:
                    return r["hit"]
        return None

    def test_pointer_hit_by_skill_agent_and_file(self):
        t0 = time.time() - 5000
        for tool, names in ((("Skill", {"skill": "testing-guide"}), {"skills": ["testing-guide"]}),
                            (("Skill", {"skill": "some-plugin:testing-guide"}), {"skills": ["testing-guide"]}),
                            (("Agent", {"subagent_type": "tester"}), {"agents": ["tester"]}),
                            (("Read", {"file_path": "/h/.ai-rules/rules/domains/testing.md"}), {"rules": ["testing"]}),
                            (("Read", {"file_path": "/p/.fieldbook/bank/06-gotchas.md"}), {"memory": ["06-gotchas.md"]})):
            path = self.transcript([self.user(t0), self.reply(t0 + 5, tools=[tool]), self.user(t0 + 60)])
            did = self.decision("pointer_useful", t0, {"transcript": path, "names": names})
            outcomes.label()
            self.assertIs(self.hit_of(did), True, tool)

    def test_pointer_miss_needs_exact_names_and_same_turn(self):
        t0 = time.time() - 5000
        path = self.transcript([
            self.user(t0),
            self.reply(t0 + 5, tools=[("Read", {"file_path": "/p/src/api/testing.md"}), ("Skill", {"skill": "testing-guide-extra"})]),
            self.user(t0 + 60),
            self.reply(t0 + 65, tools=[("Skill", {"skill": "testing-guide"})]),
        ])
        did = self.decision("pointer_useful", t0, {"transcript": path, "names": {"skills": ["testing-guide"], "rules": ["testing"]}})
        self.assertEqual(outcomes.label(), 1)
        self.assertIs(self.hit_of(did), False)

    def test_unfinished_or_empty_turns_are_not_labelled(self):
        now = time.time()
        fresh = self.transcript([self.user(now - 30), self.reply(now - 20)])
        d1 = self.decision("pointer_useful", now - 30, {"transcript": fresh, "names": {"skills": ["x"]}})
        outcomes.label()
        self.assertIsNone(self.hit_of(d1), "the turn may still be running")

    def test_turn_with_no_reply_and_missing_transcript_not_labelled(self):
        t0 = time.time() - 5000
        path = self.transcript([self.user(t0), self.user(t0 + 60)])
        d1 = self.decision("pointer_useful", t0, {"transcript": path, "names": {"skills": ["x"]}})
        d2 = self.decision("pointer_useful", t0, {"transcript": str(self.tmp / "nope.jsonl"), "names": {}})
        d3 = self.decision("pointer_useful", t0, {"names": {}})
        self.assertEqual(outcomes.label(), 0)
        self.assertEqual([self.hit_of(d) for d in (d1, d2, d3)], [None, None, None])

    def test_model_hit_is_next_turn_main_conversation_only(self):
        t0 = time.time() - 5000
        switched = self.transcript([self.user(t0), self.reply(t0 + 5, "claude-opus-5-5"),
                                    self.user(t0 + 20, "<local-command-stdout>Set model to `claude-haiku-5-5`</local-command-stdout>"),
                                    self.user(t0 + 60), self.reply(t0 + 65, "claude-haiku-5-5")])
        d1 = self.decision("model_suggestion_useful", t0, {"transcript": switched, "suggested": "claude-haiku-5-5"})
        outcomes.label()
        self.assertIs(self.hit_of(d1), True)

    def test_model_miss_and_subagent_does_not_count(self):
        t0 = time.time() - 5000
        stayed = self.transcript([self.user(t0), self.reply(t0 + 5, "claude-opus-5-5"),
                                  self.reply(t0 + 6, "claude-haiku-5-5", sidechain=True),
                                  self.user(t0 + 60), self.reply(t0 + 62, "claude-haiku-5-5", sidechain=True),
                                  self.reply(t0 + 65, "claude-opus-5-5")])
        d1 = self.decision("model_suggestion_useful", t0, {"transcript": stayed, "suggested": "claude-haiku-5-5"})
        outcomes.label()
        self.assertIs(self.hit_of(d1), False)

    def test_model_suggestion_without_a_next_turn_waits(self):
        t0 = time.time() - 5000
        path = self.transcript([self.user(t0), self.reply(t0 + 5, "claude-opus-5-5")])
        d1 = self.decision("model_suggestion_useful", t0, {"transcript": path, "suggested": "claude-haiku-5-5"})
        self.assertEqual(outcomes.label(), 0)
        self.assertIsNone(self.hit_of(d1))

    def test_label_is_idempotent_and_skips_unacted_and_old(self):
        t0 = time.time() - 5000
        path = self.transcript([self.user(t0), self.reply(t0 + 5, tools=[("Skill", {"skill": "a"})]), self.user(t0 + 60)])
        self.decision("pointer_useful", t0, {"transcript": path, "names": {"skills": ["a"]}})
        decide.decide("pointer_useful", {}, ctx={"transcript": path, "names": {}}, rng=NEVER)   # answer False
        old = self.decision("pointer_useful", time.time() - outcomes.MAX_AGE_SECONDS - 100, {"transcript": path, "names": {}})
        self.assertEqual(outcomes.label(), 1)
        self.assertEqual(outcomes.label(), 0)
        self.assertIsNone(self.hit_of(old))

    def test_block_content_prompts_tool_results_and_bad_lines(self):
        t0 = time.time() - 5000
        entries = [
            {"timestamp": iso(t0), "message": {"role": "user", "content": [{"type": "text", "text": "do it"}]}},
            self.reply(t0 + 5, tools=[("Bash", {"command": "ls"})]),
            {"timestamp": iso(t0 + 6), "message": {"role": "user", "content": [{"type": "tool_result", "content": "ok"}]}},
            self.reply(t0 + 8, tools=[("Skill", {"skill": "testing-guide"})]),
            {"timestamp": iso(t0 + 60), "message": {"role": "user", "content": [{"type": "text", "text": "next"}]}},
        ]
        path = self.tmp / "blocks.jsonl"
        path.write_text("not json at all\n" + "\n".join(json.dumps(e) for e in entries) + "\n{broken\n")
        did = self.decision("pointer_useful", t0, {"transcript": str(path), "names": {"skills": ["testing-guide"]}})
        self.assertEqual(outcomes.label(), 1)
        self.assertIs(self.hit_of(did), True, "a tool result does not end the turn")

    def test_injected_and_command_entries_do_not_start_a_turn(self):
        """A summary, a meta note or a command echo between the prompt and the reply is not a new prompt."""
        t0 = time.time() - 5000
        not_prompts = [
            {"timestamp": iso(t0 + 2), "isMeta": True, "message": {"role": "user", "content": "Caveat: generated by a command"}},
            {"timestamp": iso(t0 + 3), "isCompactSummary": True, "message": {"role": "user", "content": "This session is being continued"}},
            {"timestamp": iso(t0 + 4), "message": {"role": "user", "content": [{"type": "text", "text": "<command-name>/model</command-name>"}]}},
            {"timestamp": iso(t0 + 5), "message": {"role": "user", "content": "<local-command-stdout>ok</local-command-stdout>"}},
            {"timestamp": iso(t0 + 6), "message": {"role": "user", "content": [{"type": "text", "text": "   "}]}},
        ]
        entries = [self.user(t0)] + not_prompts + [self.reply(t0 + 8, tools=[("Skill", {"skill": "testing-guide"})]),
                                                   self.user(t0 + 60, "next")]
        did = self.decision("pointer_useful", t0, {"transcript": self.transcript(entries), "names": {"skills": ["testing-guide"]}})
        self.assertEqual(outcomes.label(), 1)
        self.assertIs(self.hit_of(did), True, "the reply still belongs to the first prompt's turn")
        for e in not_prompts:
            self.assertFalse(outcomes._is_prompt(e), e)
        self.assertTrue(outcomes._is_prompt({"message": {"role": "user", "content": [{"type": "text", "text": "real"}]}}))
        self.assertFalse(outcomes._is_prompt({"isSidechain": True, "message": {"role": "user", "content": "sub"}}))

    def test_timestamps(self):
        self.assertAlmostEqual(outcomes._ts("2026-11-18T10:00:00.123Z"), outcomes._ts("2026-11-18T12:00:00.123+02:00"), places=3)
        self.assertEqual(outcomes._ts("2026-11-18T10:00:00"), outcomes._ts("2026-11-18T10:00:00Z"))
        self.assertIsNone(outcomes._ts("nonsense"))
        self.assertIsNone(outcomes._ts(None))


class SessionState(Sandbox):
    def test_update_round_trip_and_non_dict_file(self):
        with session.update("abc") as s:
            s["n"] = 1
        self.assertEqual(session.load("abc"), {"n": 1})
        (self.shared / "state" / "abc.json").write_text("[1]")
        self.assertEqual(session.load("abc"), {})
        with session.update("abc") as s:
            s["n"] = s.get("n", 0) + 1
        self.assertEqual(session.load("abc"), {"n": 1})

    def test_lock_in_use_is_not_cleaned_up_as_old(self):
        with session.update("keep") as st:
            st["n"] = 1
        lock = self.shared / "state" / "keep.lock"
        ancient = time.time() - 30 * 86400
        os.utime(lock, (ancient, ancient))
        os.utime(self.shared / "state" / "keep.json", (ancient, ancient))
        stray = self.shared / "state" / "gone.lock"
        stray.write_text("")
        os.utime(stray, (ancient, ancient))
        with session.update("keep") as st:
            st["n"] += 1
        self.assertTrue(lock.exists(), "the lock just taken was refreshed, so the cleanup left it")
        self.assertGreater(lock.stat().st_mtime, time.time() - 60)
        self.assertFalse(stray.exists(), "an unused old lock is cleaned up")
        self.assertEqual(session.load("keep"), {"n": 2})

    def test_no_session_id_keeps_no_state(self):
        with session.update(None) as s:
            s["n"] = 5
        self.assertEqual(session.load(None), {})
        self.assertFalse((self.shared / "state" / "nosession.json").exists())

    def test_ids_are_sanitised(self):
        with session.update("../../etc/passwd") as s:
            s["x"] = 1
        self.assertEqual(sorted(p.name for p in (self.shared / "state").iterdir() if p.suffix == ".json"), ["etcpasswd.json"])

    def test_reset_keeps_model_only(self):
        with session.update("s") as st:
            st.update(model="m", shown=["a"], n=4)
        session.reset("s")
        self.assertEqual(session.load("s"), {"model": "m"})

    def test_concurrent_updates_do_not_lose_counts(self):
        import threading

        def bump():
            with session.update("race") as st:
                n = st.get("n", 0)
                time.sleep(0.005)
                st["n"] = n + 1
        threads = [threading.Thread(target=bump) for _ in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self.assertEqual(session.load("race")["n"], 8)
