---
name: Braess Router
description: A monochrome precision traffic instrument.
colors:
  bg: "#080808"
  ink: "#f5f5f2"
  muted: "#a2a2a2"
  line: "#303030"
  secondary-copy: "#aaa"
  evidence-bg: "#eeeeea"
  evidence-ink: "#101010"
  evidence-muted: "#626262"
  evidence-line: "#c6c6c3"
  button-hover: "#cecece"
  phase-selected: "#ededeb"
  phase-hover: "#222"
typography:
  display:
    fontFamily: "Archivo, Helvetica, sans-serif"
    fontSize: "clamp(58px, 6.7vw, 96px)"
    fontWeight: 400
    lineHeight: 0.99
    letterSpacing: "-.04em"
  headline:
    fontFamily: "Archivo, Helvetica, sans-serif"
    fontSize: "clamp(32px, 3.4vw, 49px)"
    fontWeight: 400
    lineHeight: 1.12
    letterSpacing: "-.035em"
  title:
    fontFamily: "Archivo, Helvetica, sans-serif"
    fontSize: "21px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "-.025em"
  body:
    fontFamily: "Archivo, Helvetica, sans-serif"
    fontSize: "16px"
    fontWeight: 400
    lineHeight: 1.5
  label:
    fontFamily: "Archivo, Helvetica, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
  action:
    fontFamily: "Archivo, Helvetica, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.5
  instrument-id:
    fontFamily: "monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: ".05em"
rounded:
  square: "0"
  circle: "50%"
spacing:
  page-gutter: "clamp(22px, 5vw, 80px)"
  small: "8px"
  regular: "20px"
  group: "24px"
  wide: "30px"
components:
  button-primary:
    backgroundColor: "{colors.ink}"
    textColor: "{colors.bg}"
    typography: "{typography.action}"
    rounded: "{rounded.square}"
    padding: "15px 20px"
  button-primary-hover:
    backgroundColor: "{colors.button-hover}"
  phase-button:
    backgroundColor: "transparent"
    textColor: "{colors.muted}"
    typography: "{typography.label}"
    padding: "11px 18px"
  phase-button-selected:
    backgroundColor: "{colors.phase-selected}"
    textColor: "{colors.bg}"
  phase-button-hover:
    backgroundColor: "{colors.phase-hover}"
    textColor: "#fff"
---

# Design System: Braess Router

## Overview

**Creative North Star: "Precision traffic instrument"**

A precision traffic instrument: near-black space, porcelain type, graphite paths, and geometric particles make routing decisions visible. Archivo carries both expressive headlines and compact controls; fine rules organize the page without raised containers.

The interface stays monochrome. Shape, position, outline, and explicit labels distinguish outcomes. Motion shares a single clock and can stop on a complete frame; the evidence remains readable independently of the animation.

**Key Characteristics:**

- Monochrome contrast with a light evidence surface.
- Regular-weight Archivo headlines and compact, tabular data.
- Flat sections, fine rules, square actions, and circular instrument geometry.
- Meaningful particle shapes with optional shared-clock motion.

## Colors

Porcelain foregrounds and graphite detail sit on a near-black field; the evidence section reverses the relationship onto pale paper.

### Primary

- **Porcelain ink** (`ink`): headlines, primary actions, strong counts, and moving particles.

### Neutral

- **Near-black** (`bg`): the principal canvas and reversed action text.
- **Graphite** (`line`): section dividers and structural rules.
- **Muted silver** (`muted`, `secondary-copy`): supporting copy and compact instrument labels.
- **Evidence paper** (`evidence-bg`): the full-width evidence section; `evidence-ink`, `evidence-muted`, and `evidence-line` supply its text and rules.
- **Control neutrals** (`button-hover`, `phase-selected`, `phase-hover`): interactive state changes without chromatic signaling.

**The Shape Carries Meaning Rule.** Use circles, squares, triangles, hollow circles, and crosses to distinguish outcomes within the monochrome field.

## Typography

**Display and Body Font:** Archivo, with Helvetica and sans-serif fallbacks. Regular and semibold faces are self-hosted under the SIL Open Font License. Monospace appears only in instrument metadata and the aperture's small mechanism labels.

The display is large, regular-weight, tightly tracked, and balanced across lines. Supporting text uses a compact editorial scale. The frontmatter records base roles; actual prose varies by context: intro (14px/1.65), mechanism explanation (13px/1.75 desktop; 14px mobile), evidence prose (14px/1.8 desktop; 13px mobile). Base body size is not a requirement to enlarge every label.

Display becomes `clamp(54px,12vw,76px)` below the mobile breakpoint. Mechanism titles become 20px. Counts use tabular figures (20px/1.2 desktop; 21px mobile). Evidence table data also uses tabular figures. Auxiliary metadata is 11px; do not generalize that size into body prose. Emphasized headline continuations use muted gray, not a heavier weight.

## Layout

A centered wrapper caps width at 1440px with the fluid page gutter. The desktop masthead is 104px high. The hero pairs its headline and 320px copy column, then gives the routing instrument the full available width. The flow stage is 410px tall, 440px at widths of at least 1500px, 350px at widths up to 1000px, and 310px at widths up to 650px.

At 1000px, mechanism rows change from four columns to three, placing their link beneath the description. At 650px, the headline and copy stack, mechanism rows use a 45px icon column plus content, evidence becomes one column, and the footer wraps. Mobile navigation retains GitHub while section links are hidden. The diagram remains horizontal; secondary endpoint labels, instrument identifier, and aperture mechanism text disappear to preserve room for route names.

Ruled rows establish local rhythm (34px vertical padding desktop, 26px mobile). Main section breathing room contracts on mobile: mechanism padding changes from 130px/110px to 76px/65px. Evidence uses 86px/90px desktop and 60px/58px mobile. These are observed surface measurements, not a universal spacing scale.

## Elevation & Depth

No box shadows are used. Depth comes from subdued path opacity, particle trails, a double-ring aperture, and the evidence surface's tonal inversion. The aperture masks intersecting paths with the background color. Its fine radial ticks belong to the instrument, not a container treatment.

**The Flat Instrument Rule.** Use rules, whitespace, and tonal inversion for hierarchy; keep surfaces free of drop shadows.

## Shapes

Actions and phase selectors are square-cornered. Thin straight rules divide sections and table rows. Circular geometry is reserved for signals, endpoints, aperture, and particle meanings; triangles and squares distinguish routed categories. Icons are inline stroked SVG, not text glyphs. No shipping raster assets are required.

## Components

### Primary action

A porcelain rectangle with semibold dark text and a rightward SVG arrow. Minimum height is 48px with a 30px content gap; hover changes its fill over 0.2s. The mobile hero action uses 11px text, 12px padding, and a 12px gap. Keyboard focus uses a 2px ink outline offset by 6px.

### Phase selectors and playback

Three inline buttons expose selection through `aria-pressed`; the selected phase inverts onto a light fill. Unselected hover uses a dark gray fill and white text. Phase buttons have minimum heights of 42px desktop and 44px mobile; final mobile horizontal padding is 7px. Playback is a transparent icon-and-label button with a 44px minimum height; mobile hides the visible label while retaining its accessible name.

### Navigation and text links

Desktop navigation uses 13px gray text, a 36px gap, and an ink hover. Repository and documentation links use inline SVG arrows. Mechanism and footer links underline on hover. The evidence download link has a persistent lower rule and a dark focus outline suitable for its light surface.

### Mechanism rows and evidence table

Mechanisms are open, ruled rows with a linework icon, title, description, and link; they are not cards. The evidence table uses collapsed borders, 19px cell padding vertically, right-aligned request counts, centered concurrency, and 11px column headings. No input fields, chips, dialogs, or elevated card primitives are shipped.

### Routing instrument

A Canvas field combines curved tracks, geometric particles, endpoint stubs, a central aperture, and HTML labels. General traffic is circular, coding square, reasoning triangular, fallback hollow, and rejection crossed. A single animation clock drives traffic and the aperture orbit. Pause freezes that clock; reduced motion initializes a complete paused frame. Offscreen and hidden-document rendering stops. Phase selection changes the story, recorded counts, and sampled traffic; illustrative durations are 5.4s for accepted paths and 2.6s for rejected paths. These durations are visual motion parameters, not latency measurements.

## Do's and Don'ts

### Do:

- **Do** distinguish traffic with geometry and labels.
- **Do** preserve visible keyboard focus and a complete reduced-motion frame.
- **Do** use the self-hosted Archivo faces and inline SVG linework.
- **Do** keep measured counts distinct from illustrative particle timing.

### Don't:

- **Don't** add color accents, generic glows, or decorative texture.
- **Don't** turn the flat ruled sections into elevated feature cards.
- **Don't** rely on motion or color alone to communicate an outcome.
