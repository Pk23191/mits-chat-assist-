---
name: Academic Intelligence
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#404940'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#707a6f'
  outline-variant: '#bfc9bd'
  surface-tint: '#1f6c3a'
  primary: '#004c22'
  on-primary: '#ffffff'
  primary-container: '#166534'
  on-primary-container: '#93e0a2'
  inverse-primary: '#8bd79b'
  secondary: '#006d30'
  on-secondary: '#ffffff'
  secondary-container: '#92f5a4'
  on-secondary-container: '#007233'
  tertiary: '#004b1e'
  on-tertiary: '#ffffff'
  tertiary-container: '#00662b'
  on-tertiary-container: '#54e97d'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#a6f4b5'
  primary-fixed-dim: '#8bd79b'
  on-primary-fixed: '#00210b'
  on-primary-fixed-variant: '#005226'
  secondary-fixed: '#95f8a7'
  secondary-fixed-dim: '#79db8d'
  on-secondary-fixed: '#00210a'
  on-secondary-fixed-variant: '#005323'
  tertiary-fixed: '#6bff8f'
  tertiary-fixed-dim: '#4ae176'
  on-tertiary-fixed: '#002109'
  on-tertiary-fixed-variant: '#005321'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  display-hero:
    fontFamily: Plus Jakarta Sans
    fontSize: 40px
    fontWeight: '700'
    lineHeight: 48px
    letterSpacing: -0.02em
  display-hero-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.015em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-md:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 20px
    fontWeight: '600'
    lineHeight: 28px
  title-md:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 24px
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
  label-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '500'
    lineHeight: 20px
  label-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.02em
  code-snippet:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
rounded:
  sm: 0.25rem
  DEFAULT: 0.5rem
  md: 0.75rem
  lg: 1rem
  xl: 1.5rem
  full: 9999px
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 2rem
  margin-mobile: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2rem
---

## Brand & Style
The design system balances the gravitas and trust of an established engineering institution with the forward-moving dynamism of modern generative AI tooling. Designed for students, researchers, and faculty, the interface evokes focus, academic rigor, intellectual calm, and high utility.

The aesthetic philosophy is **Modern Academic Utility**: clean high-clarity surfaces, generous breathing room, disciplined structure, and quiet technical confidence. It rejects gimmicky futuristic tropes (no harsh neon glows or illegible dark-mode cyber themes) in favor of crisp readability, deliberate spatial rhythm, structured citation systems, and institutional accountability. The emotional tone is reassuring, empowering, and strictly compliant.

## Colors
The color architecture reinforces institutional trust with deep forest greens, supported by luminous emerald accents and clinical slate neutrals.

- **Primary (`#166534`)**: Deep academic green. Used for authoritative anchor points, primary navigation states, master CTA surfaces, and verified institutional badges.
- **Secondary (`#15803D`)**: Active mid-tone green. Applied for secondary interactive elements, active sidebar selections, and progressive highlights.
- **Tertiary / Accent (`#22C55E`)**: Vibrant emerald. Reserved for positive confirmation markers, AI generation status indicators, streaming caret pulses, and success badges.
- **Page Background (`#F8FAFC`)**: A pale, cool slate ground that prevents glare during prolonged study sessions.
- **Surface White (`#FFFFFF`)**: Pure crisp white for cards, modal dialogs, editor panels, and elevated modules.
- **Typography Scale**: `#0F172A` (Slate 900) for primary titles and heavy reading surfaces; `#64748B` (Slate 500) for metadata, footnotes, and subtle UI hints.
- **Structural Outlines (`#E2E8F0`)**: Low-contrast borders for neat card demarcation and tabular data separation without visual fragmentation.

## Typography
Typography is paired to deliver distinct roles:
- **Headings & Titles**: **Plus Jakarta Sans** provides friendly yet geometric discipline for headers, section markers, and hero greetings, lending modern energy without sacrificing authority.
- **Body & Controls**: **Inter** handles all sustained reading, AI conversational responses, prompt inputs, system alerts, and data dense lists due to its neutral proportions and legibility at scale.
- **Code & Citations**: **JetBrains Mono** is introduced strictly for code blocks, syllabus course codes, and algorithmic notation.

## Layout & Spacing
The layout follows a fluid 12-column grid system capped at a maximum workspace width of 1440px for broad displays, transitioning to a focused single-column flow on mobile viewport sizes.

- **Desktop (1024px+)**: 12 columns with 24px (`1.5rem`) gutters and 32px (`2rem`) outer canvas margins. Features a persistent collapsable 280px left navigation rail for academic modules, syllabus navigation, and chat history.
- **Tablet (768px - 1023px)**: 8 columns with 20px gutters and 24px margins. Navigation docks into an off-canvas drawer.
- **Mobile (< 768px)**: 4 columns with 16px (`1rem`) gutters and 16px (`1rem`) canvas margins. Primary workspace collapses into an unencumbered single-column feed with fixed top status and bottom pinned interaction trays.
- **Spacing Rhythm**: Derived strictly from an 8-point structural system, maintaining clear separation between contextual prompt surfaces, research papers, citation cards, and system status boards.

## Elevation & Depth
Elevation is maintained using subtle, clean, ambient drop shadows combined with hairline outlines (`1px solid #E2E8F0`). Heavy, saturated shadows are avoided to maintain an academic document feel.

- **Level 0 (Flat)**: Pinned canvas backgrounds, prompt input containers, and structural page segment dividers.
- **Level 1 (Card / Rest)**: `0 1px 3px 0 rgba(15, 23, 42, 0.05), 0 1px 2px -1px rgba(15, 23, 42, 0.03)` wrapped with a `#E2E8F0` border. Standard state for chat response containers, resource cards, and syllabus items.
- **Level 2 (Hover / Elevated)**: `0 4px 6px -1px rgba(15, 23, 42, 0.07), 0 2px 4px -2px rgba(15, 23, 42, 0.04)`. Applied to interactive cards on hover, quick-action chips, and floating citation tooltips.
- **Level 3 (Overlays / Modals / Menus)**: `0 20px 25px -5px rgba(15, 23, 42, 0.08), 0 8px 10px -6px rgba(15, 23, 42, 0.03)` paired with backdrop-blur (`backdrop-blur-sm` over `rgba(15, 23, 42, 0.3)`). Applied to institutional policy modals, document preview sheets, and source inspect panels.

## Shapes
A dual-tier roundedness rule organizes content hierarchically:
- **Structural Cards & Surfaces**: Standardized at a firm `12px` (`0.75rem`), balancing modern softness with architectural order suited for academic data, course schedules, and research blocks.
- **Interactive Triggers & Source Tags**: Rendered as continuous pills (`9999px`) for prompt chips, verified tags, compliance status badges, and circular utility buttons, differentiating actionable items from static structural panels.
- **Input Fields**: Standardized at `8px` (`0.5rem`) for compact form fields, expanding to `16px` for the primary floating generative prompt bar.

## Components

### Buttons
- **Primary**: Solid `#166534` background, white label, full pill shape (`rounded-full`) or `8px` border radius depending on density. Subtle hover transition to `#15803D`.
- **Secondary / Subtle**: Outlined `1px solid #E2E8F0`, surface `#FFFFFF`, text `#0F172A`. Hover transitions surface to `#F8FAFC`.
- **AI Action / Emerald Accent**: Background `rgba(34, 197, 94, 0.12)`, text `#166534`, border `1px solid rgba(34, 197, 94, 0.3)`. Used for contextual generation triggers (e.g., "Summarize Unit", "Draft Assignment Outline").

### Verified Source Tags & Compliance Badges
- **Verified Institutional Source Tag**: Full pill geometry, background `#F0FDF4`, border `1px solid #BBF7D0`, text `#166534`, leading checkmark or institute emblem icon. Used to explicitly validate that an AI response is grounded in approved MITS departmental syllabus or circular records.
- **Compliance Status Badge**: Pill geometry, background `#F8FAFC`, border `1px solid #E2E8F0`, muted text `#64748B`. States include "AI Generated", "Peer Reviewed", or "Curriculum Aligned".

### Input Fields & Prompt Bar
- **Conversational Master Input**: Elevated white surface container with `16px` radius, bordered in `#E2E8F0`, subtle Level 1 shadow. Expands dynamically with multi-line prompts. Active focus transitions border to `#166534` with an outer ring of `rgba(22, 101, 52, 0.15)`.
- **Form Text Fields**: `8px` corner radius, `#FFFFFF` background, `#E2E8F0` border, `14px` typography with `#64748B` placeholder styling.

### Cards
- **Content & Chat Bubble Cards**: `#FFFFFF` background, `12px` corner radius, `1px solid #E2E8F0` perimeter border. Distinct user and AI bubbles: User bubbles feature a soft slate tint (`#F1F5F9`), while AI outputs use crisp white cards with an institutional deep-green citation footer.

### Chips & Filters
- **Filter Chips**: Pill shaped with small padding (`6px 14px`), default state `#FFFFFF` border `#E2E8F0`, text `#64748B`. Active state changes to `#166534` background with pure white text.

### Citation & Evidence Drawer
- Pinned slide-over or floating card surface showing raw excerpts from MITS Gwalior course syllabi, past question banks, or academic circulars, highlighting exact text matches with a subtle `#DCFCE7` highlight backdrop.