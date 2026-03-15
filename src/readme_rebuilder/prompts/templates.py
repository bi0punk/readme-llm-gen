README_BASE_TEMPLATE = """# {title}

> {tagline}

## Overview

{overview}

## Features

{features}

## Architecture

{architecture}

## Prerequisites

{prerequisites}

## Installation

{installation}

## Configuration

{configuration}

## Usage

{usage}

## Testing

{testing}

## Docker

{docker}

## Repository Notes

{repository_notes}

## Limitations

{limitations}

## Next Steps

{next_steps}
"""

BLUEPRINT_PROMPT = """
You are a senior technical writer and software architect.
Create a factual README blueprint for a local software project.

Rules:
- Use only the supplied evidence.
- Prefer source code, manifests, tree output, and git metadata over the existing README.
- Never invent commands, frameworks, integrations, ports, environment variables, or deployment steps.
- If something is uncertain, phrase it conservatively.
- Keep bullets short, technical, and directly actionable.
- Return structured output matching the schema exactly.
- Agrega una descripcion de que es o que trata de hacer el proyecto , antes de los detalles.
README base template:
{base_template}

Directory tree:
{tree_text}

Heuristic facts:
{heuristic_facts}

Git context:
{git_context}

Existing README (secondary evidence; treat carefully):
{existing_readme}

Primary context digest:
{primary_context}

Secondary context digest:
{secondary_context}
"""

BLUEPRINT_PROMPT_FAST = """
You are a technical writer. Create a README blueprint from the evidence below.
Return structured output matching the schema. Be concise. Do not invent anything.

Tree:
{tree_text}

Facts:
{heuristic_facts}

Files:
{selected_file_snippets}
"""

PRIMARY_CONTEXT_PROMPT = """
You are analyzing a software project to prepare a high-quality README.

Rules:
- Use only the supplied evidence.
- Be concise and technical.
- Cite uncertainty as open questions instead of making assumptions.
- Return structured output only.

Project tree:
{tree_text}

Heuristic facts:
{heuristic_facts}

Git context:
{git_context}

Existing README:
{existing_readme}

Primary file snippets:
{primary_file_snippets}
"""

GAP_ANALYSIS_PROMPT = """
You are reviewing the project context gathered so far.

Rules:
- Detect only meaningful information gaps for writing the README.
- Focus on setup, usage, testing, configuration, docker, architecture.
- If the project is already well-covered, return an empty gaps list.
- Return structured output only.

Context digest:
{primary_context}
"""

SECONDARY_CONTEXT_PROMPT = """
You are enriching the README context for a local software project.

Rules:
- Focus only on the missing areas requested.
- Use only the supplied evidence.
- Return structured output only.

Current context digest:
{primary_context}

Requested missing areas:
{requested_gaps}

Secondary file snippets:
{secondary_file_snippets}
"""
