"""Durable resume across Python processes, source restoration, attempt limits and history."""
import asyncio
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

from app.workflow.persistent import RequestJournal, exclusive_run, inspect_checkpoints
from app.retrieval.settings import RetrievalSettings
from app.retrieval.web import WebSources
from checks.check_web_retrieval import Response


class ProcessRecoveryChecks(unittest.TestCase):
    def worker(self,root,*args,expected=0):
        process=subprocess.run([sys.executable,"-m","checks.checkpoint_worker","--root",str(root),*map(str,args)],
                               capture_output=True,text=True,timeout=45)
        self.assertEqual(process.returncode,expected,process.stderr[-3500:]+process.stdout[-1000:])
        return json.loads(process.stdout.splitlines()[-1]) if process.returncode==0 else None

    def test_pause_exit_resume_and_terminal_idempotence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            first=self.worker(root,"--pause");directory=Path(first["artifacts_dir"])
            self.assertEqual(first["status"],"paused");self.assertEqual(first["model_calls"],2)
            self.assertEqual(first["tool_calls"],1);self.assertEqual(first["pending_nodes"],["model"])
            self.assertTrue((directory/"sources.json").exists())
            second=self.worker(root,"--resume",directory)
            self.assertEqual(second["status"],"answered");self.assertEqual(second["model_calls"],7)
            self.assertEqual(second["tool_calls"],2);self.assertEqual(second["actual_model_attempts"],7)
            self.assertEqual(first["thread_id"],second["thread_id"])
            self.assertEqual(len(second["trace"]),2);self.assertFalse(second["resumable"])
            again=self.worker(root,"--resume",directory)
            self.assertEqual(again["actual_model_attempts"],7);self.assertEqual(again["actual_tool_attempts"],2)
            self.assertEqual(len(again["trace"]),2)
            history=asyncio.run(inspect_checkpoints(directory))
            self.assertGreater(len(history["snapshots"]),1)
            self.assertEqual(history["snapshots"][0]["next"],[])
            self.assertEqual(len(list((directory/"attempts").glob("*.json"))),3)

    def test_hard_process_death_and_recovery(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);self.worker(root,"--crash",expected=23)
            directory=next(root.iterdir())
            prior=asyncio.run(inspect_checkpoints(directory))["snapshots"][0]
            self.assertEqual(prior["model_calls"],2);self.assertEqual(prior["tool_calls"],1)
            result=self.worker(root,"--resume",directory)
            self.assertEqual(result["status"],"answered")
            self.assertEqual(result["model_calls"],7)
            self.assertEqual(result["actual_model_attempts"],8)  # Uncertain crashed attempt is counted.
            self.assertEqual(result["actual_tool_attempts"],2)
            self.assertEqual(len(result["trace"]),2)

    def test_changed_code_manifest_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            first=self.worker(Path(tmp),"--pause");directory=Path(first["artifacts_dir"])
            manifest=json.loads((directory/"session.json").read_text());manifest["code_fingerprint"]="changed"
            (directory/"session.json").write_text(json.dumps(manifest))
            process=subprocess.run([sys.executable,"-m","checks.checkpoint_worker","--root",tmp,"--resume",str(directory)],capture_output=True,text=True,timeout=30)
            self.assertNotEqual(process.returncode,0)
            self.assertIn("Code/session version changed",process.stderr)


class StorageChecks(unittest.TestCase):
    def test_source_registry_cache_survives_new_instance(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"sources.json";settings=RetrievalSettings(backend="web")
            session=Mock();web=WebSources(settings,session,path)
            session.request.return_value=Response(json.dumps({"query":{"search":[{"title":"Python"}]}}).encode())
            source_id=web.search_sources("Python")["results"][0]["source_id"]
            web._fetch=Mock(return_value={"title":"Python","text":"async support","content_hash":
                "sha256:"+__import__('hashlib').sha256(b"async support").hexdigest()})
            first=web.read_source(source_id)
            restored=WebSources(settings,Mock(),path)
            self.assertEqual(restored.read_source(source_id),first)
            restored.session.get.assert_not_called()
            self.assertEqual(restored.search_sources("Python")["results"][0]["source_id"],source_id)
            restored.session.request.assert_not_called()
            data=json.loads(path.read_text());data["cache"][source_id]["text"]="tampered"
            path.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError,"hash mismatch"):WebSources(settings,Mock(),path)

    def test_model_journal_replay_and_limit_survive_reopen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);model=Mock(return_value={"content":"{}"})
            journal=RequestJournal(root,1,1);self.assertEqual(journal.model(model)([],[]),{"content":"{}"})
            reopened=RequestJournal(root,1,1)
            self.assertEqual(reopened.model(model)([],[]),{"content":"{}"});model.assert_called_once()
            with self.assertRaisesRegex(ValueError,"attempt limit"):reopened.model(model)([{"role":"user","content":"new"}],[])

    def test_single_writer_lock(self):
        with tempfile.TemporaryDirectory() as tmp:
            with exclusive_run(Path(tmp)):
                with self.assertRaisesRegex(ValueError,"already active"):
                    with exclusive_run(Path(tmp)):pass


if __name__=="__main__":unittest.main()
