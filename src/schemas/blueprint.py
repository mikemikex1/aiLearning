"""Pydantic schema for the Planner's blueprint.json output."""
from __future__ import annotations
from typing import List
from pydantic import BaseModel, Field


class Module(BaseModel):
    name: str
    responsibility: str
    inputs: List[str] = Field(default_factory=list)
    outputs: List[str] = Field(default_factory=list)


class CLIArg(BaseModel):
    name: str
    type: str
    required: bool = False
    default: str | None = None


class Blueprint(BaseModel):
    project_id: str
    title: str
    topic: str
    objective: str
    tech_stack: List[str]
    modules: List[Module]
    entrypoint: str = "main.py"
    cli_args: List[CLIArg] = Field(default_factory=list)
    edge_cases: List[str] = Field(default_factory=list)
    success_criteria: List[str] = Field(default_factory=list)
