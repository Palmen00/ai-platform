# Development Rules

## Core Rules

- Always split code into small modules
- Do not put too much logic in one file
- Frontend should use components and hooks
- Frontend styling, theme, fonts, and UI text must not be hardcoded in ways that block future customization
- Anything that is reasonably expected to vary should be centralized as configuration instead of being scattered as hardcoded values
- Backend should separate routes and business logic
- Scripts must be split into focused, composable files instead of long monolithic blocks
- Reuse existing components and API layers before adding new abstractions
- Keep naming consistent across the project
- Prefer clean architecture over shortcuts that create coupling

## Before Adding Features

- Check the existing structure first
- Reuse the current API layer where possible
- Fit new code into existing naming and module boundaries
- Check whether the change affects cleanup, deployment, or persistent storage behavior

## Future-Proofing

- Use environment variables for configuration
- Avoid hardcoded values
- Design with Docker deployment in mind
- Keep data directories explicit and predictable
- Plan for safe cleanup of caches, temp files, and replaced deploy artifacts
- Prepare the frontend for localization, theming, and centralized typography control

## Configuration Rules

- Centralize values that may change across language, theme, branding, deployment, or product evolution
- Prefer shared config, design tokens, constants, and settings layers over repeated literals
- Keep defaults in one place so a visual or product-wide change can be made once and applied everywhere
- Do not over-abstract stable business logic just to avoid literals; configuration should target things that are realistically variable
- Avoid hidden magic values for spacing, colors, sizes, copy, limits, paths, and feature toggles

## Frontend UI Rules

- Theme support must be designed centrally, not patched component by component
- Dark mode should be supported without duplicating component logic
- Fonts should be defined through a shared typography layer or config
- UI text should be easy to extract for multiple languages
- Avoid scattering color values, font declarations, and literal UI strings across the codebase
- Keep visual primitives such as colors, spacing, radius, shadows, and typography tokens centralized
- Keep reusable labels, product copy, and navigation text out of component internals when they are likely to change
- Follow `Docs/ui-style-guide.md` as the default visual direction for admin and product UI
- Prefer compact, text-first navigation and avoid oversized buttons, cards, and blocks unless the content truly needs them
- Keep layouts minimal and information-dense so more useful content fits without unnecessary scrolling

## Script Design Rules

- Keep each script responsible for one job
- Prefer shared helper scripts or functions over duplicated shell blocks
- Avoid large scripts where a small mistake can break unrelated behavior
- Separate install, update, start, stop, and cleanup into different entry points
- Scripts that can delete data must target only known directories and use explicit paths
- Cleanup logic must never silently remove user data or shared model storage

## Deployment And Storage Rules

- Windows is the development environment, not the primary production target
- Ubuntu 24 is the primary deployment target
- Persistent data must live outside versioned app code
- New deploys must be replaceable without leaving behind large unused artifacts
- Model assets should be managed once and reused across app updates where possible

## AI Collaboration Context

When generating or refactoring code for this project, optimize for modularity, reuse, and long-term maintainability. The target system is a scalable self-hosted AI platform with a Next.js frontend and a FastAPI backend communicating with Ollama.

## Current Build Priorities

Right now, changes should optimize for:

- stable retrieval and grounded answer quality
- predictable operations, diagnostics, cleanup, and recovery
- maintainable deployment flows for Ubuntu 24
- incremental automation rather than broad platform expansion

## Current Anti-Goals

Avoid pulling the project back into early over-scope. In the current phase, do not prioritize:

- broad agent frameworks
- large connector systems
- marketplace-style extensions
- desktop-specific product branching for Windows
