# Search and agent discovery

Reviewed against primary documentation on 2026-09-21. This is an implementation record, not a ranking or AI-citation claim. Only the explicit asset list in `scripts/check_site.py` is published.

## Intent and identity

The page serves developers looking for a Jev router, Rust semantic routing, and Poise endpoint selection. The title, description, visible introduction and SoftwareSourceCode entity describe those actual capabilities. Braess remains an independent single-server alpha. There are no invented customers, ratings, pricing offers, production benchmarks, or official TypeSafe affiliations.

## Published artifacts

- HTML contains its useful content without JavaScript, one primary heading, absolute canonical, descriptive title and description, index/follow metadata, and complete Open Graph/Twitter image metadata.
- Embedded JSON-LD links WebSite, WebPage and SoftwareSourceCode identities to the actual repository and maintainer. This is semantic description, not a claim of eligibility for Google's software-app rich results.
- `assets/social-card.png` is a 1200×630 authored preview rendered from `assets/social-card.svg`. The PNG records source provenance. The SVG source and licensed self-hosted Archivo fonts are also public.
- `sitemap.xml` lists the canonical HTML URL only. No automatic lastmod, made-up update frequency or priority values.
- `llms.txt` is a scoped, curated documentation index. `index.md` provides a readable Markdown representation of the product, mechanism and experiment scope. HTML advertises both with `alternate` and `describedby` links, following the llms.txt v2 proposal.
- WOFF2 font files total 54,308 bytes, down from 222,580 bytes of TTF. This is a byte reduction, not a field-performance claim.

## Crawler policy and host constraints

The effective policy is https://copyleftdev.github.io/robots.txt, at the origin root. At inspection it returned HTTP 200 and allowed `*`, OAI-SearchBot, GPTBot, Claude-SearchBot and other named crawlers. A project-level `/braess-router/robots.txt` would not control these crawlers and is deliberately not shipped. Host-level training preferences remain unchanged; search inclusion and model training are different controls.

GitHub Pages controls CDN caching and HTTP headers. No custom header support, origin-root policy change or crawler-IP access guarantee is claimed by this repository. The project sitemap is directly accessible and linked; submission to search consoles remains an account operation.

## Verification and maintenance

Run `python3 scripts/test_site.py` and `python3 scripts/check_site.py`. Pages CI checks metadata consistency, canonical and subpath links, JSON-LD identity, sitemap URLs, image dimensions, safe assets, Markdown discovery, and replay-data consistency. Eight tests exercise valid content and rejection of broken discovery artifacts.

For publication, compare the hosted asset bytes with the checked-out sources and check replay behavior on desktop/mobile and with JavaScript disabled. Lighthouse is a lab diagnostic; a score does not prove indexing, traffic, ranking, AI citations or real-user Core Web Vitals. Local generated reports live under ignored `artifacts/`.

When content changes, update HTML and its Markdown representation together. Keep factual software claims aligned with repository docs. If routing facts or brand copy change, update the source social SVG and render a fresh PNG with the self-hosted fonts. Do not refresh sitemap dates merely because a workflow ran.

## Account-level follow-through

In the owner's verified Google Search Console URL-prefix property `https://copyleftdev.github.io/braess-router/`, submit `sitemap.xml` and inspect the canonical URL. In Bing Webmaster Tools, verify/import the same site and submit the same sitemap. Track impressions, relevant query clicks, indexed canonical status and crawl errors; do not treat a successful fetch or sitemap submission as confirmed indexing. No account verification or submission has been performed in this change.

## Primary references

- [Google's 2026 generative-AI optimization guide](https://developers.google.com/search/docs/fundamentals/ai-optimization-guide): foundational SEO, useful original content and crawlability; llms.txt is not used for Google ranking or generative-search visibility.
- [Google sitemap guidance](https://developers.google.com/search/docs/crawling-indexing/sitemaps/build-sitemap): canonical URLs and submission.
- [Google robots.txt guidance](https://developers.google.com/search/docs/crawling-indexing/robots/intro): origin-root crawl policy.
- [OpenAI crawler documentation](https://developers.openai.com/api/docs/bots): OAI-SearchBot controls search; GPTBot concerns training, independently.
- [llms.txt v2 proposal](https://llmstxt.org/): scoped indexes, Markdown representations and discovery links; a proposal, not a universal crawler requirement.
- [Schema.org SoftwareSourceCode](https://schema.org/SoftwareSourceCode): repository and programming-language identity.
- [Open Graph protocol](https://ogp.me/): social object and image metadata.
