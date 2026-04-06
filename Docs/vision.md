# Vision

## Product Vision

Build the easiest way for a team to run a private AI assistant on its own infrastructure.

The product should be:

- Easy to install
- Easy to use
- Secure for internal company data
- Good enough to replace ad hoc internal AI tools

## Positioning

This is not a broad AI platform in its first form.

It starts as a self-hosted private knowledge assistant:

- Install locally
- Choose a model that fits the hardware
- Upload internal documents
- Chat with that knowledge through a clean web UI

The broader platform vision still matters, but it should grow out of a strong core workflow rather than lead the MVP.

## Problem

Local AI is still too fragmented to adopt easily.

Power users can combine tools like Ollama, web UIs, vector databases, offline knowledge sources, and Docker, but the setup is fragile and operationally noisy. There are too many moving parts, too many defaults to choose from, and too many ways for the system to fail.

Companies often respond by building internal AI tools around SharePoint, local files, and internal knowledge sources, but those efforts usually suffer from weak UX, long delivery cycles, and inconsistent quality.

## Solution

Provide a self-hosted application that installs on a clean Linux machine, recommends a sensible local model, ingests internal documents, and gives users a strong chat experience without forcing them to assemble the stack themselves.

The first product should solve one job extremely well:

Enable a team to deploy a private AI assistant for internal knowledge quickly and safely.

The practical working model is:

- Build and test locally on Windows
- Target Ubuntu 24 for real deployment
- Keep local Windows use lightweight instead of turning it into a separate full product track

## Target Audience

- Internal IT teams
- Small and medium businesses
- Consulting companies

Homelab users remain a useful early audience for testing and feedback, but the product should be designed primarily around teams with internal knowledge needs.

## Value Proposition

- Local data control
- Faster setup than assembling open source tools manually
- Better UX than most internal company-built AI tools
- Lower operating cost than API-only approaches for repeated internal usage
- A sane default path from installation to useful document chat

## Core Product Areas

- Guided installation and setup
- Hardware-aware model recommendation
- Clean web UI for chat and knowledge workflows
- UI foundations for theming, localization, and configurable typography
- Document upload and retrieval
- Basic RAG for internal knowledge
- Admin and status visibility
- Security basics such as authentication and controlled access

## Product Principles

- Optimize for the first successful install
- Optimize for the first useful answer
- Prefer strong defaults over excessive configuration
- Centralize anything likely to change so product-wide adjustments stay cheap
- Keep the architecture extensible, but do not ship platform breadth before core reliability
- Treat UX as part of the product, not a layer added afterward
- Keep deployment and cleanup predictable so the system does not accumulate waste across updates
- Do not lock language, theme, or typography into hardcoded UI decisions

## Future Product Direction

Once the core product is stable, the platform can expand with:

- Offline knowledge packs such as Kiwix-based sources
- Additional knowledge connectors
- Advanced routing across knowledge sources
- Agent-like workflows
- Broader administration and enterprise features

These should be treated as second-phase expansion, not MVP requirements.

## Key Insight

The winning early product is not "an AI operating system."

The winning early product is a private knowledge assistant that is dramatically easier to install and nicer to use than the alternatives.

## Next Steps

- Choose deployment strategy: Docker or native install
- Build the smallest reliable backend and frontend path
- Integrate Ollama and Qdrant
- Build onboarding and model selection
- Prove the install -> upload -> chat workflow end to end
- Define storage, update, and cleanup rules before the first real deployment workflow

## Current Status

The core product direction is now validated by working software:

- install -> upload -> chat works locally
- the product already behaves like a private knowledge assistant rather than a generic AI shell
- deployment, cleanup, diagnostics, and recovery are now part of the product shape, not afterthoughts

## Current Product Focus

The next product phase should stay focused on quality and reliability:

- make answers more natural and more consistently grounded
- improve retrieval ranking and source selection
- improve operations, recovery, storage management, and deployment clarity

## Later Expansion

These ideas are still valid, but intentionally later:

- offline knowledge packs
- external connectors
- watch-folder ingestion and light automations
- agent-like workflows
- broader enterprise controls
