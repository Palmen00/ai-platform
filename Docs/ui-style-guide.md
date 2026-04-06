# UI Style Guide

## Purpose

This file defines the default visual direction for the product UI so new work stays consistent across pages, not just within a single feature.

The reference direction is:

- compact
- text-first
- information-dense
- admin-console-like
- closer to Open WebUI than to a marketing site

## Core Principles

- Prefer compact navigation over large card-like menus.
- Prefer text rows, subtle separators, and small active indicators over large filled buttons.
- Keep sidebars narrow so the main content area gets most of the width.
- Use large blocks only when the content is genuinely complex or needs strong separation.
- Default to minimal surfaces before adding visual weight.
- Make hierarchy come from typography, spacing, and grouping before color and decoration.
- Keep admin and settings views practical and dense rather than expressive or playful.

## Navigation

- Sidebar navigation should be text-led and compact.
- Avoid tall navigation buttons when a single-row or two-line text item is enough.
- Active state should usually be shown with a subtle left border, text emphasis, or light background change.
- Avoid oversized pills or card-style navigation unless there is a very clear UX reason.
- Search and filters in sidebars should be compact and low-noise.

## Layout

- Favor narrow sidebars and wide content areas.
- Avoid unnecessary nested cards inside already separated sections.
- Reduce vertical height where possible so users can see more without scrolling.
- Use grids and tables for overview-heavy admin areas instead of long stacks of oversized cards.
- Keep headers informative but not oversized.

## Components

- Buttons should default to compact sizing.
- Inputs should avoid excessive height or padding.
- Cards should be used selectively, not as the default wrapper for every element.
- Tables and lists should feel clean and readable, not oversized.
- Secondary helper text should be present when useful, but concise.

## Visual Weight

- Use decoration sparingly.
- Minimize heavy shadows, oversized radius, and oversized badges unless they add clear value.
- Prefer subtle contrast differences over dramatic container changes.
- Keep the UI feeling light and efficient.

## When Large Blocks Are Allowed

Larger blocks are still appropriate when:

- the user is reviewing a complex status area
- the content mixes controls and explanation that need breathing room
- the block is a true summary surface or major form section

If the content is simple, do not wrap it in a large block just because other sections use blocks.

## Product Rule Of Thumb

When in doubt, choose the version that:

1. shows more useful information above the fold
2. takes less horizontal and vertical space
3. uses fewer decorative containers
4. still remains readable and calm

## Current House Style

For this project, the default house style is now:

- compact settings navigation
- smaller global sidebar
- text-based admin navigation
- minimal, practical control surfaces
- fewer oversized UI elements

New UI work should follow this style unless there is a specific reason to diverge.
