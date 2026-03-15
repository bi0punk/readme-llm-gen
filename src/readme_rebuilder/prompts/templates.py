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

# Prompts iterativos (reservados para un flujo multi-etapa futuro)
PRIMARY_CONTEXT_PROMPT = """
You are analyzing a local software project to prepare a high-quality README.

Rules:
- Use only the supplied evidence.
- Be concise and technical.
- Extract likely purpose, architecture notes, setup clues, usage clues, testing clues, and docker clues.
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

SECONDARY_CONTEXT_PROMPT = """
You are enriching a technical README context for a local software project.

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

# Prompt principal — flujo actual de un solo paso LLM
BLUEPRINT_PROMPT = """
You are a senior technical writer and software architect.
Create a factual README blueprint for a local software project.

Rules:
- Use the README base template structure as the target shape.
- Prefer source code, manifests, tree output, and git metadata over the existing README.
- Do not invent commands, frameworks, integrations, or deployment steps.
- If something is uncertain, state it conservatively.
- Keep every bullet short, technical, and useful.
- Return structured output matching the schema exactly.

README base template:
{base_template}

Directory tree:
{tree_text}

Heuristic facts (languages, frameworks, entrypoints, env vars, commands detected):
{heuristic_facts}

Git context:
{git_context}

Existing README (secondary evidence — treat with skepticism):
{existing_readme}

Selected file snippets:
{selected_file_snippets}
"""
