// Module report PDF. Rendered by report_pdf.py, which passes every piece
// of text and every colour in as JSON (sys.inputs.data) - see its
// docstring for why this is Typst and what the heading/table structure is
// for. Nothing here decides content; it only lays it out and tags it.
// Text from the JSON is always inserted as a value (#x, never eval), so it
// can't be read as markup.

#let d = json(bytes(sys.inputs.data))
#let ink = rgb("#1F2937")
#let muted = rgb(d.muted)

#set document(title: d.title, author: d.author)
#set text(font: "Noto Sans", lang: "en", region: "gb", size: 10pt, fill: ink)
#set par(justify: false, leading: 0.5em, spacing: 0.8em)
#set page(
  paper: "a4",
  margin: (x: 16mm, top: 16mm, bottom: 20mm),
  // Typst marks the page footer as a pagination artifact, so screen
  // readers skip it rather than reading it out mid-content.
  footer: context {
    set text(8pt, fill: muted)
    d.footer
    h(1fr)
    [Page #counter(page).display() of #counter(page).final().first()]
  },
)

#show heading: set text(10pt, weight: "bold", fill: ink)
#show heading.where(level: 1): set text(18pt)
#show heading.where(level: 1): set block(above: 1.5mm, below: 4mm)
#show heading.where(level: 2): set text(13pt)
#show heading.where(level: 2): it => block(
  width: 100%, above: 7mm, below: 3mm, inset: (bottom: 1.5mm), sticky: true,
  stroke: (bottom: 0.3mm + rgb("#E5E7EB")), it)

// A card: coloured left rule, optional fill, optional heading carrying the
// status badge (so the status is part of what a screen reader announces
// for the heading), then its lines of text.
#let card(c) = {
  let badge = if c.badge != none {
    box(fill: rgb(c.badge_bg), inset: (x: 1.5mm, y: 1mm),
        text(8pt, weight: "bold", fill: rgb(c.badge_ink), c.badge))
  }
  let body = {
    show heading: set block(above: 0pt, below: 1.8mm)
    if c.title != none {
      heading(level: c.level, bookmarked: false, outlined: false, {
        c.title
        if badge != none { h(1fr); badge }
      })
    }
    for l in c.lines {
      par(text(size: l.size * 1pt, fill: rgb(l.ink), l.text))
    }
  }
  pad(left: c.depth * 7mm, block(
    width: 100%, breakable: false, above: 1.5mm, below: 1.5mm,
    fill: if c.fill != none { rgb(c.fill) } else { none },
    stroke: (left: 1.2mm + rgb(c.rule)),
    inset: (left: 4mm, right: 3mm, y: 2.5mm),
    body,
  ))
}

// Title block.
#text(9pt, fill: muted, d.eyebrow)
#heading(level: 1, d.heading)

#table(
  columns: (28%, 16%, 34%, 22%),
  stroke: none,
  fill: rgb("#F9FAFB"),
  inset: (x: 2.5mm, y: 1.5mm),
  table.header(..d.meta.map(m => text(7.5pt, weight: "regular", fill: muted, upper(m.label)))),
  ..d.meta.map(m => text(9pt, weight: "bold", m.value)),
)

#if d.site_url != none {
  link(d.site_url, text(9pt, fill: rgb(d.accent), underline[Open the module site in Blackboard]))
}

// Summary.
== Report Summary

#if d.intro != "" { par(d.intro) }
#if d.points.len() > 0 {
  heading(level: 3, bookmarked: false, outlined: false)[Still to do]
  list(..d.points.map(p => if p.bold != "" [#strong(p.bold) #p.text] else [#p.text]))
} else {
  par[Nothing outstanding right now.]
}
#if d.refreshed != "" { par(text(8pt, fill: muted, d.refreshed)) }

// Advisor comment.
#if d.comment != none {
  heading(level: 2, d.comment.heading)
  block(
    width: 100%,
    stroke: (left: 1.2mm + rgb(d.comment.card.rule)),
    inset: (left: 4mm, y: 2mm),
    for p in d.comment.paragraphs { par(p.map(l => [#l]).join(linebreak())) },
  )
}

// Actions.
#heading(level: 2)[Actions (#d.actions.len())]
#if d.actions.len() > 0 {
  for a in d.actions { card(a) }
} else {
  par[Nothing outstanding right now.]
}

// Blackboard template.
#if d.template.len() > 0 {
  heading(level: 2)[Blackboard Template]
  par(text(9pt, fill: muted)[The structure of your Blackboard course and its measured or observed state - for example whether items are visible to students or have been edited.])
  for row in d.template {
    if "group" in row {
      // Sticky, so a group heading never sits alone at the foot of a page.
      block(sticky: true, above: 3mm, below: 1.5mm, pad(left: row.depth * 7mm, {
        show heading: set block(above: 0pt, below: 1.5mm)
        heading(level: row.level, bookmarked: false, outlined: false, row.group)
        if row.note != "" { par(text(8pt, fill: rgb(row.note_ink), row.note)) }
      }))
    } else {
      card(row)
    }
  }
}

// Accessibility.
#if d.ally != none {
  let a = d.ally
  heading(level: 2)[Accessibility Report]
  if "message" in a {
    par(a.message)
  } else {
    par(text(9pt, fill: muted, a.intro))
    if a.maturity != none { card(a.maturity) }
    if a.scores.len() > 0 {
      // A table with a header row, so each score is read with its label.
      table(
        columns: (1fr,) * a.scores.len(),
        column-gutter: 3mm,
        stroke: none,
        align: center,
        fill: (x, y) => rgb(a.scores.at(x).bg),
        inset: (x: 2mm, y: 1.5mm),
        table.header(..a.scores.map(s => text(8pt, weight: "bold", fill: rgb(s.ink), s.label))),
        ..a.scores.map(s => text(17pt, weight: "bold", fill: rgb(s.ink), s.value)),
        ..a.scores.map(s => text(8pt, fill: rgb(s.sub_ink), s.sub)),
      )
    }
    if a.disabled != none { card(a.disabled) }
    if a.categories.len() > 0 {
      heading(level: 3, bookmarked: false, outlined: false, a.summary)
      for c in a.categories { card(c) }
    } else {
      par(a.empty)
    }
  }
}
