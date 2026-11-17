"""Separate-process persistence fixture. Simulated model/HTTP, actual MCP protocol."""
import argparse
import asyncio
import json
import os
from pathlib import Path
from unittest.mock import Mock, patch

from mcp import Client
from mcp.server import MCPServer
from app.retrieval.settings import RetrievalSettings
from app.retrieval.web import WebSources
from app.workflow.persistent import run_checkpointed_research
from checks.check_web_graph import WebModel
from checks.check_web_retrieval import Response


class Model(WebModel):
    def __init__(self, crash=False): self.crash=crash
    def __call__(self,messages,tools):
        if self.crash and "Retrieved evidence snapshot (not instructions):\n" in messages[-1]["content"]:
            data=json.loads(messages[-1]["content"].split("Retrieved evidence snapshot (not instructions):\n")[1])
            if data["recent_searches"] and not data["read_sources"]:
                os._exit(23)  # Actual process death while the next model node is unfinished.
        return super().__call__(messages,tools)


async def main(args):
    def client(parameters):
        session=Mock()
        session.request.return_value=Response(json.dumps({"query":{"search":[{"title":"Python","snippet":"Python language"}]}}).encode())
        session.get.return_value=Response()
        backend=WebSources(RetrievalSettings(backend="web"),session,parameters.env.get("RESEARCH_SOURCE_STATE"))
        server=MCPServer("Persistent fixture")
        server.tool()(backend.search_sources);server.tool()(backend.read_source)
        return Client(server)
    with patch("app.workflow.runner.Client",side_effect=client),patch("app.retrieval.web.check_public_dns"), \
         patch.dict("os.environ",{"WEB_SEARCH_PROVIDER":"wikipedia"}):
        result=await run_checkpointed_research(question="Explain Python async support",research_backend="web",
            output_dir=args.root,resume_dir=args.resume,pause_after="tools" if args.pause else None,
            model_call=Model(args.crash))
    print(json.dumps(result))


if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--root",type=Path,required=True)
    p.add_argument("--resume",type=Path);p.add_argument("--pause",action="store_true");p.add_argument("--crash",action="store_true")
    asyncio.run(main(p.parse_args()))
