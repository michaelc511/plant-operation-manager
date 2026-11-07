"""Generate the three fictional plant documents used as the app's knowledge sources.

Writes to docs/:
  - safety_procedures.pdf        (EHS-SOP-001)
  - maintenance_manual.pdf       (MM-100)
  - quality_control_standards.pdf (QC-STD-200)

All content is fictional sample data for development and testing.
Requires reportlab (Python 3.10+):  pip install reportlab
Run from the project root:          python tools/scripts/generate_sample_docs.py
"""

from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas as rl_canvas
from reportlab.platypus import (
    KeepTogether,
    ListFlowable,
    ListItem,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

OUT_DIR = Path(__file__).resolve().parents[2] / "docs"
COMPANY = "Northfield Components Inc. - Plant 2 (Riverside)"
DISCLAIMER = "FICTIONAL SAMPLE DOCUMENT - for software development and testing only"

# ---------------------------------------------------------------- styles
_ss = getSampleStyleSheet()
ACCENT = colors.HexColor("#1F4E79")
STYLES = {
    "title": ParagraphStyle("t", parent=_ss["Title"], fontSize=22, leading=27, textColor=ACCENT, spaceAfter=6),
    "subtitle": ParagraphStyle("st", parent=_ss["Normal"], fontSize=12, alignment=TA_CENTER, textColor=colors.HexColor("#444444"), spaceAfter=14),
    "h1": ParagraphStyle("h1", parent=_ss["Heading1"], fontSize=15, leading=19, textColor=ACCENT, spaceBefore=14, spaceAfter=6),
    "h2": ParagraphStyle("h2", parent=_ss["Heading2"], fontSize=12, leading=15, textColor=colors.HexColor("#222222"), spaceBefore=8, spaceAfter=4),
    "p": ParagraphStyle("p", parent=_ss["BodyText"], fontSize=10, leading=13.5, spaceAfter=6),
    "cell": ParagraphStyle("c", parent=_ss["BodyText"], fontSize=8.8, leading=11),
    "cellh": ParagraphStyle("ch", parent=_ss["BodyText"], fontSize=8.8, leading=11, textColor=colors.white, fontName="Helvetica-Bold"),
    "note": ParagraphStyle("n", parent=_ss["BodyText"], fontSize=9.5, leading=12.5),
}


# ---------------------------------------------------------------- content builders
def H1(t): return ("h1", t)
def H2(t): return ("h2", t)
def P(t): return ("p", t)
def UL(*items): return ("ul", list(items))
def OL(*items): return ("ol", list(items))
def TABLE(rows, widths=None): return ("table", rows, widths)
def WARN(t): return ("warn", t)
def NOTE(t): return ("note", t)


def _callout(text, bg, border, label):
    para = Paragraph(f"<b>{label}</b> {text}", STYLES["note"])
    t = Table([[para]], colWidths=[6.5 * inch])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 1, border),
        ("LEFTPADDING", (0, 0), (-1, -1), 8), ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    return [Spacer(1, 4), t, Spacer(1, 8)]


def _table(rows, widths):
    data = [[Paragraph(escape(str(c)), STYLES["cellh"]) for c in rows[0]]]
    data += [[Paragraph(escape(str(c)), STYLES["cell"]) for c in r] for r in rows[1:]]
    if widths:
        widths = [w * inch for w in widths]
    t = Table(data, colWidths=widths, repeatRows=1, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#EEF3F8")]),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#9AA9B8")),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    return [t, Spacer(1, 8)]


def _list(items, ordered):
    flow = [ListItem(Paragraph(i, STYLES["p"]), leftIndent=14) for i in items]
    kw = {"bulletType": "1", "bulletFormat": "%s."} if ordered else {"bulletType": "bullet", "start": "•"}
    return [ListFlowable(flow, leftIndent=16, bulletFontSize=9, **kw)]


def build_story(meta, blocks):
    story = [
        Spacer(1, 0.3 * inch),
        Paragraph(meta["title"], STYLES["title"]),
        Paragraph(f"{meta['doc_no']} &nbsp;|&nbsp; Revision {meta['rev']} &nbsp;|&nbsp; Effective {meta['effective']}", STYLES["subtitle"]),
    ]
    story += _table([
        ["Field", "Value"],
        ["Facility", COMPANY],
        ["Document owner", meta["owner"]],
        ["Approved by", meta["approved"]],
        ["Applies to", meta["applies"]],
        ["Review cycle", meta["review"]],
    ], [1.6, 4.9])
    story += _callout(DISCLAIMER + ". Names, equipment, part numbers and values are invented.",
                      colors.HexColor("#F2F2F2"), colors.HexColor("#999999"), "Note:")

    pending_h = []  # keep headings with the block that follows them
    for b in blocks:
        kind = b[0]
        if kind in ("h1", "h2"):
            pending_h.append(Paragraph(b[1], STYLES[kind]))
            continue
        if kind == "p":
            fl = [Paragraph(b[1], STYLES["p"])]
        elif kind == "ul":
            fl = _list(b[1], ordered=False)
        elif kind == "ol":
            fl = _list(b[1], ordered=True)
        elif kind == "table":
            fl = _table(b[1], b[2])
        elif kind == "warn":
            fl = _callout(b[1], colors.HexColor("#FDECEA"), colors.HexColor("#C0392B"), "WARNING:")
        elif kind == "note":
            fl = _callout(b[1], colors.HexColor("#EAF2FB"), ACCENT, "NOTE:")
        else:
            raise ValueError(kind)
        if pending_h:
            story.append(KeepTogether(pending_h + fl[:1]))
            story += fl[1:]
            pending_h = []
        else:
            story += fl
    return story


def make_canvas(meta):
    class NumberedCanvas(rl_canvas.Canvas):
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self._saved = []

        def showPage(self):
            self._saved.append(dict(self.__dict__))
            self._startPage()

        def save(self):
            total = len(self._saved)
            for state in self._saved:
                self.__dict__.update(state)
                self._decorate(total)
                super().showPage()
            super().save()

        def _decorate(self, total):
            w, h = letter
            self.setStrokeColor(ACCENT)
            self.setLineWidth(0.6)
            self.line(0.75 * inch, h - 0.6 * inch, w - 0.75 * inch, h - 0.6 * inch)
            self.line(0.75 * inch, 0.65 * inch, w - 0.75 * inch, 0.65 * inch)
            self.setFont("Helvetica", 8)
            self.setFillColor(colors.HexColor("#444444"))
            self.drawString(0.75 * inch, h - 0.5 * inch, COMPANY)
            self.drawRightString(w - 0.75 * inch, h - 0.5 * inch, meta["title"])
            self.drawString(0.75 * inch, 0.48 * inch, f"{meta['doc_no']} Rev {meta['rev']}  |  Effective {meta['effective']}")
            self.drawRightString(w - 0.75 * inch, 0.48 * inch, f"Page {self._pageNumber} of {total}")
            self.setFont("Helvetica-Oblique", 7)
            self.drawCentredString(w / 2, 0.32 * inch, DISCLAIMER + "  |  Uncontrolled when printed")
    return NumberedCanvas


def render(filename, meta, blocks):
    path = OUT_DIR / filename
    doc = SimpleDocTemplate(
        str(path), pagesize=letter,
        leftMargin=0.85 * inch, rightMargin=0.85 * inch, topMargin=0.85 * inch, bottomMargin=0.9 * inch,
        title=meta["title"], author="Northfield Components (fictional)", subject=meta["subject"],
        keywords=meta["keywords"],
    )
    doc.build(build_story(meta, blocks), canvasmaker=make_canvas(meta))
    print(f"wrote {path.relative_to(OUT_DIR.parent)}")


# ====================================================================== SAFETY
SAFETY_META = dict(
    title="Plant Safety Procedures", doc_no="EHS-SOP-001", rev="D", effective="2026-03-01",
    owner="Environment, Health and Safety (EHS) Manager", approved="Plant Manager; EHS Manager",
    applies="All employees, contractors and visitors on the Plant 2 production floor",
    review="Annually, and after any serious incident or process change",
    subject="safety procedures", keywords="safety, PPE, lockout tagout, LOTO, guarding, hazmat, emergency",
)

SAFETY = [
    H1("1. Purpose and Scope"),
    P("This procedure sets the minimum safety requirements for work on the Plant 2 production floor: "
      "Line 1 (CNC machining), Line 2 (pressing and welding), Line 3 (assembly and packing) and the "
      "support areas (compressor room, parts-washing bay and shipping dock). Where an equipment "
      "manual or quality standard conflicts with this procedure, <b>this procedure takes precedence</b>."),
    P("Related documents: MM-100 Equipment Maintenance Manual; QC-STD-200 Quality Control Standards; "
      "Safety Data Sheets (SDS) for all chemicals on site."),

    H1("2. Roles and Responsibilities"),
    TABLE([
        ["Role", "Responsibilities"],
        ["Floor supervisor", "Enforces this procedure on their shift; verifies PPE and lockout compliance; leads the pre-shift safety talk (5 minutes); completes incident form EHS-F-07; performs evacuation headcount."],
        ["Employee / operator", "Follows this procedure; inspects own PPE before use; stops work and reports any unsafe condition; never bypasses a guard or interlock."],
        ["Maintenance technician", "Applies lockout/tagout before any servicing; removes and reinstalls guards; returns equipment to service only after guards and interlocks are verified."],
        ["EHS department", "Owns this procedure; trains employees; investigates incidents; manages permits, SDS library and PPE stock."],
        ["Contractors", "Follow this procedure plus any contract-specific safety plan; must be escorted until site orientation is completed."],
    ], [1.6, 4.9]),
    P("Every employee has <b>stop-work authority</b>: anyone may stop a task they believe is unsafe, without penalty. "
      "The supervisor must review the concern before work restarts."),

    H1("3. General Shop-Floor Rules"),
    UL(
        "Walk only in the green-marked pedestrian walkways. Yellow lanes are reserved for forklifts.",
        "No personal phones or earbuds on the production floor outside the break rooms.",
        "Loose clothing, jewelry (including rings) and hair longer than shoulder length must be secured near rotating equipment.",
        "Keep aisles, electrical panels (0.9 m / 36 in clearance), fire extinguishers and eyewash stations clear at all times.",
        "Report all injuries, near misses and unsafe conditions to the floor supervisor immediately (see Section 11).",
        "No food or drink at workstations. Hydration stations are located at the end of each line.",
    ),

    H1("4. Personal Protective Equipment (PPE)"),
    H2("4.1 Baseline PPE"),
    P("The following PPE is required for everyone entering the production floor, including visitors:"),
    UL(
        "Safety glasses with side shields meeting ANSI Z87.1.",
        "Safety-toe footwear meeting ASTM F2413.",
        "Hearing protection (plugs or muffs) in all of Line 2 and the compressor room, where noise exceeds 85 dBA. "
        "Hearing protection is optional elsewhere unless posted.",
    ),
    H2("4.2 Task-Specific PPE Matrix"),
    P("The PPE below is required <b>in addition to</b> baseline PPE."),
    TABLE([
        ["Task / area", "Additional PPE required", "Notes"],
        ["CNC lathe operation (CNC-201/202/203)", "None beyond baseline. NO gloves while the spindle is turning.", "Gloves can be caught by rotating parts."],
        ["Removing chips and swarf", "Cut-resistant gloves, ANSI A4 or higher", "Spindle must be stopped. Use a chip hook, never bare hands."],
        ["Handling machined or stamped parts with sharp edges (A-102, B-220, C-310)", "Cut-resistant gloves, ANSI A2 or higher", "Applies to inspection and packing too."],
        ["Hydraulic press HP-400 operation", "Hearing protection (Line 2 area)", "Two-hand controls and light curtain must be active."],
        ["Die change on HP-400", "Cut-resistant gloves A4, safety-toe boots with metatarsal guard", "Lockout required (Section 5)."],
        ["Robotic welding cell RW-510 (entry for tip change or teach)", "Welding jacket (FR), leather gloves, face shield over safety glasses", "Robot must be in locked-out or teach mode at reduced speed (max 250 mm/s)."],
        ["Manual welding / grinding", "Auto-darkening helmet shade 10-13, FR jacket, leather gauntlet gloves", "Hot work permit required outside the welding bay (Section 8.1)."],
        ["Solvent parts washer PW-1 (normal use)", "Nitrile gloves (minimum 15 mil), chemical splash goggles, chemical-resistant apron", "Local exhaust ventilation must be running."],
        ["PW-1 solvent change or tank cleaning, or exhaust ventilation not running", "All of the above plus half-face respirator with organic vapor cartridges", "Respirator users must be fit-tested within the last 12 months."],
        ["Coolant mixing / sump cleaning (Line 1)", "Nitrile gloves, splash goggles", "Coolant sump pit entry is confined space (Section 8.2)."],
        ["Compressed air for cleaning", "Face shield over safety glasses", "Nozzle must be OSHA-compliant, under 30 psi dead-end pressure. Never aim at a person."],
        ["Forklift operation", "High-visibility vest", "Seat belt must be worn."],
    ], [1.9, 2.4, 2.2]),
    WARN("Never wear gloves when operating a lathe, drill or any machine with an exposed rotating spindle. "
         "Gloves are allowed only when the spindle is fully stopped."),
    H2("4.3 PPE Inspection and Replacement"),
    P("Inspect PPE before each use. Replace cut-resistant gloves when torn or saturated with oil, safety glasses when scratched "
      "enough to impair vision, and respirator cartridges every 40 hours of use or immediately if the wearer smells solvent. "
      "Replacement PPE is issued at the tool crib on any shift."),

    H1("5. Lockout/Tagout (LOTO) - Control of Hazardous Energy"),
    H2("5.1 When Lockout Is Required"),
    P("Lockout is required before any person places any part of their body into a point of operation or danger zone, and for:"),
    UL(
        "Servicing, maintenance, lubrication or repair (unless the MM-100 task is explicitly rated as \"running lubrication\" from outside the guard).",
        "Clearing jams on conveyor CV-3, HP-400, the CNC lathes or the case packer.",
        "Removing, adjusting or replacing any machine guard.",
        "Die changes, tooling changes that require reaching into the machine, and welding tip changes on RW-510.",
        "Any work on electrical, hydraulic or pneumatic components.",
    ),
    NOTE("There is <b>no minor-servicing exception</b> for hydraulic press HP-400. Every entry into the HP-400 die area requires full lockout and ram blocks."),
    H2("5.2 The Six-Step Lockout Procedure"),
    OL(
        "<b>Prepare and notify.</b> Identify all energy sources using the table in Section 5.3. Tell the operator and the floor supervisor that the machine is being locked out.",
        "<b>Shut down.</b> Stop the machine using its normal stop control.",
        "<b>Isolate.</b> Open the main disconnect and close or bleed each additional energy-isolating device (air, hydraulic, gravity).",
        "<b>Apply locks and tags.</b> Each worker applies their own personal red lock and a tag showing their name, date and reason. Never use another person's lock.",
        "<b>Release stored energy.</b> Bleed accumulators and air lines, block or lower raised parts, and let moving parts come to a complete stop.",
        "<b>Verify zero energy.</b> Press the start button and check gauges to confirm the machine cannot start. Return controls to OFF afterward.",
    ),
    H2("5.3 Energy Sources by Equipment"),
    TABLE([
        ["Equipment", "Energy sources", "Isolation points"],
        ["Hydraulic press HP-400 (Line 2)", "Electrical 480 V; hydraulic (accumulator up to 3,000 psi); gravity (ram)", "Disconnect DS-400; accumulator bleed valve HV-2 (verify gauge reads 0 psi); two ram safety blocks from the red storage rack"],
        ["Conveyor CV-3 (Line 3)", "Electrical 480 V; gravity on incline section", "Disconnect DS-3C; chock the incline belt with the yellow belt clamp"],
        ["CNC lathes CNC-201/202/203 (Line 1)", "Electrical 480 V; pneumatic 90 psi (chuck)", "Machine main disconnect; air valve AV-2xx with lockable dump"],
        ["Robotic welder RW-510 (Line 2)", "Electrical 480 V; pneumatic; weld power; robot arm gravity", "Disconnect DS-510; air valve AV-510; place arm in home position before lockout"],
        ["Air compressor AC-1 (compressor room)", "Electrical 480 V; stored air in 500 gal receiver", "Disconnect DS-AC1; close outlet valve and drain receiver to 0 psi"],
        ["Parts washer PW-1", "Electrical 120 V (pump)", "Unplug and apply plug lockout cover"],
        ["Case packer CP-3 (Line 3)", "Electrical 480 V; pneumatic 80 psi", "Disconnect DS-CP3; air valve AV-CP3"],
    ], [1.7, 2.3, 2.5]),
    H2("5.4 Group Lockout and Shift Change"),
    P("When several people work on the same equipment, use the group lockbox at the line station: the lead technician locks the "
      "isolation points and places the keys in the lockbox, then every worker applies a personal lock to the lockbox. "
      "At shift change, the <b>oncoming worker applies their lock before the off-going worker removes theirs</b>, so the "
      "equipment is never left without protection."),
    H2("5.5 Removing Another Person's Lock"),
    P("A lock may be removed only by the person who applied it. If that person has left the site, the lock may be removed only "
      "with written authorization from both the Plant Manager and the EHS Manager, after documented attempts to contact the "
      "worker, and the worker must be told before they resume work."),

    H1("6. Machine Guarding"),
    UL(
        "Never operate a machine with a guard removed, damaged, or bypassed, or with an interlock defeated.",
        "Guards may be removed, adjusted or replaced only by maintenance technicians, and only with the machine locked out (Section 5).",
        "<b>A guard must never be removed or replaced while the line is running.</b> Only the machine being worked on must be "
        "locked out; adjacent machines on the same line may keep running only if they do not share an energy source and a "
        "barricade is placed at least 1 m (3 ft) from the work area.",
        "After reinstalling a guard, the technician tests the interlock and the supervisor signs the return-to-service line on the work order before production restarts.",
        "If a guard is found damaged or missing, stop the machine, hang a yellow \"DO NOT OPERATE\" tag and notify maintenance and the supervisor.",
    ),
    H2("6.1 Start-of-Shift Safeguard Checks"),
    TABLE([
        ["Equipment", "Check", "Pass criterion"],
        ["HP-400 light curtain", "Pass the 30 mm test rod slowly through the full height of the curtain while the press is in inch mode", "Press stops every time the rod breaks the beam"],
        ["HP-400 two-hand control", "Release one button during the stroke", "Ram stops immediately"],
        ["CNC lathe door interlocks", "Open the door with spindle commanded at low speed", "Spindle will not start or stops within 2 s"],
        ["RW-510 cell gate", "Open the gate in auto mode", "Robot stops; fault shown on pendant"],
        ["CV-3 emergency pull-cords", "Pull cord at each of 3 stations (one station per day, rotating)", "Conveyor stops; reset required"],
    ], [1.7, 2.9, 1.9]),
    P("Any failed check means the machine must not run. Tag it out and notify maintenance; record the failure on the shift log."),

    H1("7. Hazardous Materials and Chemicals"),
    H2("7.1 Safety Data Sheets and Labels"),
    P("SDS for every chemical are kept in the yellow SDS binder at each line station and on the plant intranet. All secondary "
      "containers (spray bottles, transfer cans) must carry a label with the product name and hazard pictograms."),
    H2("7.2 Parts Washer PW-1 Solvent"),
    P("PW-1 uses SafeClean 150, a petroleum-naphtha solvent with a flash point of 61 °C (142 °F)."),
    UL(
        "No open flames, grinding, welding or other ignition sources within 6 m (20 ft) of PW-1.",
        "Keep the lid closed when not actively cleaning parts. The lid has a fusible link that closes it automatically in a fire.",
        "Local exhaust ventilation must be running during use; if it is not, stop use or wear a respirator (see Section 4.2).",
        "Store spare solvent only in the flammable-liquids cabinet in the parts-washing bay (maximum 60 gal / 227 L in the cabinet).",
        "Used solvent goes in the red drum labeled \"Hazardous Waste - Spent Solvent\". Never pour solvent into floor drains.",
    ),
    H2("7.3 Spill Response"),
    TABLE([
        ["Spill size", "Who responds", "Action"],
        ["Small: under 5 L (about 1 gal) and not near a drain", "Trained employee in the area", "Wear task PPE; contain with the spill kit at the line station; place used absorbent in the hazardous waste drum; tell the supervisor."],
        ["Large: 5 L or more, any amount entering a floor drain, or any unknown chemical", "EHS emergency response", "Leave the area, warn others, call emergency extension 5555; the supervisor keeps people out until EHS clears the area."],
    ], [1.9, 1.5, 3.1]),

    H1("8. Work Permits"),
    H2("8.1 Hot Work Permit"),
    P("Welding, cutting, brazing or grinding outside the designated welding bay requires a hot work permit from EHS. "
      "The permit is valid for one shift only. Remove combustibles within 11 m (35 ft) or cover them with fire blankets. A fire "
      "watch with an extinguisher must stay during the work and for <b>30 minutes</b> after it ends."),
    H2("8.2 Confined Space Entry"),
    P("The Line 1 coolant sump pit and the inside of the 500 gal compressor receiver are permit-required confined spaces. "
      "Entry requires an EHS entry permit, an attendant outside the space at all times, and atmospheric testing before and "
      "during entry. Acceptable atmosphere: oxygen 19.5% to 23.5%, flammable gas below 10% of LEL, hydrogen sulfide below "
      "10 ppm and carbon monoxide below 35 ppm."),

    H1("9. Emergency Response"),
    H2("9.1 Emergency Contacts"),
    TABLE([
        ["Situation", "Contact"],
        ["Fire, serious injury, large spill, gas leak", "Emergency extension 5555 (staffed 24/7); then 911 if directed"],
        ["First aid needed", "Floor supervisor; first-aid kits at each line station and in the break room"],
        ["EHS on-call (nights and weekends)", "Via the security desk, extension 5000"],
    ], [2.6, 3.9]),
    H2("9.2 Fire"),
    P("Use the RACE response: <b>R</b>escue anyone in immediate danger, <b>A</b>larm (pull station and call 5555), "
      "<b>C</b>onfine the fire by closing doors, <b>E</b>xtinguish only if the fire is small and you are trained, or Evacuate. "
      "Operate extinguishers using PASS: Pull, Aim, Squeeze, Sweep. Never fight a fire involving PW-1 solvent larger than a wastebasket."),
    H2("9.3 Evacuation"),
    P("When the alarm sounds, stop machines with the normal stop control if it is safe to do so and leave by the nearest exit. "
      "The assembly point is <b>Area B in the north parking lot</b>. The floor supervisor takes the shift roster, completes a headcount "
      "within 10 minutes and reports missing people to the incident commander. Nobody re-enters until EHS gives the all-clear."),
    H2("9.4 Injuries and Chemical Exposure"),
    UL(
        "Chemical in the eyes: flush at the nearest eyewash station for at least 15 minutes, holding the eyelids open, then seek medical evaluation.",
        "Chemical on the skin: remove contaminated clothing and rinse for 15 minutes; use the safety shower for large exposures.",
        "Cuts and lacerations: apply direct pressure; anything needing more than first aid goes to the clinic per the supervisor.",
        "Eyewash stations and safety showers are activation-tested weekly by the area supervisor and tagged with the test date.",
    ),

    H1("10. Forklift and Pedestrian Safety"),
    UL(
        "Only certified operators may drive forklifts. Certification is renewed every 3 years, or after an incident or near miss.",
        "Complete the pre-shift forklift checklist (brakes, horn, lights, forks, chains, hydraulic leaks). A failed item means the truck is tagged out.",
        "Maximum speed on the production floor is 5 mph (8 km/h); sound the horn at intersections and blind corners.",
        "Pedestrians must make eye contact with the driver before crossing a forklift lane.",
        "Never stand or walk under raised forks, and never ride on forks or pallets.",
    ),

    H1("11. Incident and Near-Miss Reporting"),
    OL(
        "Report every injury, near miss, property damage or spill to the floor supervisor immediately, before the end of the shift.",
        "The supervisor secures the scene and completes incident form <b>EHS-F-07</b> within 24 hours.",
        "Serious injuries (hospital treatment, amputation, loss of an eye, or loss of consciousness) must be reported by the supervisor to the EHS Manager <b>within 1 hour</b>.",
        "EHS leads a root-cause investigation within 5 working days and assigns corrective actions.",
    ),

    H1("12. Training Requirements"),
    TABLE([
        ["Training", "Who", "Frequency"],
        ["Safety orientation", "All new employees and contractors", "Before starting work"],
        ["Lockout/tagout (authorized)", "Maintenance technicians, setup technicians", "Initial and annually"],
        ["Lockout/tagout (affected)", "Operators and supervisors", "Initial and every 2 years"],
        ["Hazard communication / SDS", "All employees", "Initial and annually"],
        ["Respirator fit test", "PW-1 users and anyone using respirators", "Annually"],
        ["Forklift operator", "Forklift operators", "Every 3 years"],
        ["First aid / CPR", "At least 2 per shift per line", "Every 2 years"],
        ["Confined space entry", "Entrants, attendants, supervisors", "Initial and annually"],
    ], [2.3, 2.6, 1.6]),
]

# ====================================================================== MAINTENANCE
MAINT_META = dict(
    title="Equipment Maintenance Manual", doc_no="MM-100", rev="7", effective="2026-01-15",
    owner="Maintenance Manager", approved="Maintenance Manager; Plant Engineer",
    applies="Maintenance technicians, setup technicians and floor supervisors at Plant 2",
    review="Every 12 months, or when equipment is added or modified",
    subject="maintenance manual", keywords="maintenance, preventive maintenance, lubrication, troubleshooting, torque, conveyor, press, CNC",
)

MAINT = [
    H1("1. Scope and How to Use This Manual"),
    P("This manual covers preventive maintenance (PM), routine servicing and first-line troubleshooting for Plant 2 production "
      "equipment. Each equipment chapter lists specifications, PM tasks and step-by-step procedures."),
    WARN("Before any task that requires reaching into a machine, removing a guard or working on electrical, hydraulic or "
         "pneumatic parts, apply lockout/tagout as described in <b>EHS-SOP-001 Section 5</b>. Wear the PPE required by "
         "EHS-SOP-001 Section 4.2. If this manual and EHS-SOP-001 conflict, EHS-SOP-001 takes precedence."),
    P("\"Operating hours\" are read from each machine's hour meter. Plant 2 runs 3 shifts, 5 days a week, so "
      "<b>about 120 operating hours equal one calendar week</b>."),

    H1("2. Equipment Register"),
    TABLE([
        ["Equipment ID", "Description", "Location", "Manufacturer / model (fictional)", "Criticality"],
        ["CNC-201, CNC-202, CNC-203", "2-axis CNC turning centers", "Line 1", "Hartwell TL-250", "A (bottleneck)"],
        ["HP-400", "400-ton hydraulic press", "Line 2", "Brannock HPX-400", "A (bottleneck)"],
        ["RW-510", "Robotic MIG welding cell", "Line 2", "Kestrel RW-6 robot with Arcon 350 power source", "B"],
        ["CV-3", "Belt conveyor, 30 m with 8 m incline", "Line 3", "Midland Belt MB-30", "A (bottleneck)"],
        ["CP-3", "Automatic case packer", "Line 3", "Packworth CP-12", "B"],
        ["AC-1", "75 hp rotary screw air compressor with 500 gal receiver", "Compressor room", "Torrent RS-75", "A (plant-wide)"],
        ["PW-1", "Solvent parts washer, 30 gal", "Parts-washing bay", "CleanBay SW-30", "C"],
    ], [1.25, 1.6, 0.9, 1.75, 1.0]),
    P("Criticality A equipment stops the line or the plant when it fails; breakdowns must be responded to within 15 minutes. "
      "B: within 1 hour. C: within the same shift."),

    H1("3. Preventive Maintenance Schedule"),
    TABLE([
        ["Equipment", "Task", "Frequency", "Ref."],
        ["CV-3", "Visual belt tracking check", "Every shift (by operator)", "4.2"],
        ["CV-3", "Grease head, tail and take-up pulley bearings", "Every 250 operating hours (about every 2 weeks)", "4.1"],
        ["CV-3", "Check belt tension", "Monthly", "4.3"],
        ["CV-3", "Inspect drive gearbox oil level", "Monthly", "4.5"],
        ["HP-400", "Check hydraulic oil level and temperature; inspect for leaks", "Daily", "5.1"],
        ["HP-400", "Replace hydraulic return filter", "Every 1,000 operating hours, or when the filter indicator shows red", "5.3"],
        ["HP-400", "Hydraulic oil sample for lab analysis", "Quarterly", "5.2"],
        ["HP-400", "Change hydraulic oil", "Every 4,000 operating hours, or when lab cleanliness is worse than ISO 18/16/13", "5.2"],
        ["HP-400", "Lubricate gibs and slide", "Weekly", "5.1"],
        ["CNC-201/202/203", "Check way-lube reservoir; check coolant concentration and pH", "Daily", "6.1, 6.2"],
        ["CNC-201/202/203", "Grease chuck jaws", "Weekly", "6.4"],
        ["CNC-201/202/203", "Clean coolant tank and replace coolant", "Every 6 months", "6.2"],
        ["RW-510", "Replace contact tip; clean nozzle", "Every shift", "9.1"],
        ["RW-510", "Replace wire liner", "Every 6 months", "9.1"],
        ["RW-510", "Robot axis grease", "Every 5,000 operating hours", "9.2"],
        ["AC-1", "Verify receiver auto-drain operates; check oil level", "Daily", "7.1"],
        ["AC-1", "Replace air intake filter", "Every 2,000 operating hours", "7.2"],
        ["AC-1", "Change compressor oil and oil filter", "Every 4,000 operating hours", "7.2"],
        ["PW-1", "Replace solvent filter", "Monthly", "8.1"],
        ["PW-1", "Change solvent", "Every 3 months, or sooner if the solvent is dark or parts come out oily", "8.1"],
        ["PW-1", "Test lid fusible-link closure", "Quarterly", "8.2"],
    ], [1.2, 2.6, 2.1, 0.6]),

    H1("4. Conveyor CV-3 (Line 3)"),
    P("Specifications: 30 m total length including an 8 m incline at 15°; belt width 600 mm; belt speed 0.5 m/s (adjustable "
      "0.3 to 0.8 m/s by VFD); drive motor 7.5 kW (10 hp) with helical gearbox; 6 flanged pillow-block bearings "
      "(head pulley 2, tail pulley 2, take-up pulley 2)."),
    H2("4.1 Bearing Lubrication"),
    P("Interval: every 250 operating hours. Lubricant: NLGI grade 2 lithium-complex EP grease (stock code LUB-G2)."),
    OL(
        "Lock out CV-3 at disconnect DS-3C and clamp the incline belt (EHS-SOP-001 Section 5.3).",
        "Wipe each grease fitting clean before connecting the grease gun.",
        "Apply <b>2 pumps (about 3 g) per bearing</b>. Do not over-grease: excess grease pushes out the seals and causes overheating.",
        "Wipe off purged grease, remove locks, run the conveyor for 10 minutes and check that bearing temperature stays below 70 °C (158 °F) with the infrared thermometer.",
        "Record the task and bearing temperatures on the PM work order.",
    ),
    H2("4.2 Belt Tracking"),
    P("Operators check tracking every shift: the belt edge must stay at least 25 mm from the pulley frame. If the belt is "
      "drifting, notify maintenance. To adjust, lock out the conveyor, then turn the take-up adjusting screw on the side "
      "toward which the belt is drifting by a quarter turn, run for 2 minutes and re-check. Repeat until centered. "
      "Never adjust tracking with the guard removed while the belt is moving."),
    H2("4.3 Belt Tension"),
    P("With the conveyor locked out, press the return belt midway between two return idlers. Correct tension gives "
      "<b>10 mm of deflection per 1 m of span</b>. Adjust both take-up screws equally to keep tracking unchanged."),
    H2("4.4 Clearing Jams and Guards"),
    P("Never reach into CV-3 to clear a jam while it is running, even with the pull-cord stopped. Lock out at DS-3C first. "
      "Guards on CV-3 (pinch-point guards at head and tail pulleys and the incline side guards) may only be removed under "
      "lockout and must be reinstalled and checked before restart, per EHS-SOP-001 Section 6."),
    H2("4.5 Gearbox"),
    P("Check the oil sight glass monthly; it must be at mid-glass. Oil: ISO VG 220 synthetic gear oil (LUB-G220). Change every "
      "10,000 operating hours."),

    H1("5. Hydraulic Press HP-400 (Line 2)"),
    P("Specifications: 400 tons capacity; stroke 400 mm; normal operating pressure 2,800 psi (193 bar), relief valve set at "
      "3,000 psi (207 bar); reservoir 150 gal (568 L); hydraulic oil ISO VG 46 anti-wear (LUB-H46)."),
    WARN("HP-400 has no minor-servicing exception. Every entry into the die area requires full lockout, accumulator bleed to "
         "0 psi at valve HV-2, and both ram safety blocks in place (EHS-SOP-001 Section 5)."),
    H2("5.1 Daily and Weekly Checks"),
    UL(
        "Oil level must be between the MIN and MAX marks on the reservoir sight glass with the ram fully up.",
        "Normal oil temperature is 40-55 °C (104-131 °F). Above 60 °C, check the cooler fan and water flow. "
        "<b>At 65 °C (149 °F) the press must be stopped</b> until the cause is found.",
        "Look for leaks at hoses, fittings and cylinder seals. Any spraying leak means immediate shutdown: high-pressure oil can penetrate skin.",
        "Weekly: lubricate gibs and slide with way oil ISO VG 68 (LUB-W68) at the 8 lube points.",
    ),
    H2("5.2 Oil Sampling and Oil Change"),
    P("Take an oil sample quarterly from the sample port SP-1 with the press at operating temperature and send it to the lab. "
      "Change the oil every 4,000 operating hours, or sooner if the lab reports cleanliness worse than ISO 18/16/13 or water "
      "above 500 ppm."),
    OL(
        "Run the press to warm the oil to about 40 °C, then lock out and bleed the accumulator.",
        "Drain the reservoir into the waste-oil cart; remove the clean-out cover and wipe out sludge with lint-free cloths.",
        "Replace the return filter (Section 5.3) and the breather cap.",
        "Refill with new ISO VG 46 oil through a 10-micron filter cart; never pour directly from a drum.",
        "Remove locks, cycle the press 10 times empty in inch mode to purge air, and top up the oil to the MAX mark.",
    ),
    H2("5.3 Return Filter"),
    P("Replace the return-line filter element (part FE-400-10, 10 micron) every 1,000 operating hours or when the "
      "differential pressure indicator shows red, whichever comes first."),
    H2("5.4 Die Change"),
    OL(
        "Lower the ram onto the die, lock out, bleed the accumulator and insert both ram safety blocks.",
        "Unclamp and remove the die with the die cart; never slide dies by hand.",
        "Install the new die, center it with the locating pins, and torque the die clamp bolts to <b>250 N·m (184 ft·lb)</b> in a cross pattern.",
        "Remove blocks and locks, set shut height for the die per the die setup sheet, and run a first-article part for QC (QC-STD-200 Section 4).",
    ),

    H1("6. CNC Turning Centers CNC-201, CNC-202, CNC-203 (Line 1)"),
    P("Specifications: max turning diameter 250 mm; spindle up to 4,500 rpm; hydraulic chuck 8 in with 90 psi air-actuated "
      "tailstock; 60 gal coolant tank."),
    H2("6.1 Daily Checks (operator)"),
    UL(
        "Way-lube reservoir above the MIN line; top up with ISO VG 68 way oil (LUB-W68).",
        "Coolant level, concentration and pH (Section 6.2).",
        "Chip conveyor running and chip bin less than three-quarters full.",
        "Door interlock check (EHS-SOP-001 Section 6.1).",
    ),
    H2("6.2 Coolant"),
    P("Coolant: semi-synthetic CoolCut 500 (LUB-C500). Target concentration <b>6-8%</b> measured with the refractometer "
      "(refractometer factor 1.0, so a Brix reading of 7 equals 7%). Target pH 8.5-9.5. If concentration is low, add premix "
      "at 10%; if high, add water. If pH is below 8.5 or the coolant smells sour, notify maintenance for treatment or "
      "replacement. Wear nitrile gloves and splash goggles when mixing coolant."),
    H2("6.3 Spindle Warm-Up"),
    P("If the machine has been idle more than 4 hours, run warm-up program O9000 (10 minutes, stepping 500 / 1,500 / 3,000 rpm) "
      "before cutting production parts. Skipping warm-up causes thermal growth that can push the A-102 journal diameter out of tolerance."),
    H2("6.4 Chuck Maintenance"),
    P("Weekly, with the machine locked out: remove the jaws, clean the serrations and grease each jaw with chuck grease "
      "(LUB-CK) using 1 pump per fitting. Check chuck clamping pressure is 2.0-2.4 MPa on the machine gauge."),

    H1("7. Air Compressor AC-1"),
    P("Specifications: 75 hp rotary screw; output 300 cfm; cut-in pressure 95 psi, cut-out 110 psi; 500 gal receiver with "
      "electronic auto-drain; plant distribution set to 90 psi."),
    H2("7.1 Daily Checks"),
    UL(
        "Press the TEST button on the receiver auto-drain and confirm water discharges.",
        "Oil level visible in the sight glass while running.",
        "Discharge temperature below 105 °C (221 °F). Above this, check the cooler for dust blockage.",
    ),
    H2("7.2 Scheduled Service"),
    P("Replace the air intake filter (FE-AC1-A) every 2,000 operating hours. Change the oil (synthetic compressor fluid "
      "LUB-RS8) and oil filter (FE-AC1-O) every 4,000 operating hours. Replace the air-oil separator every 8,000 hours. "
      "Before service, lock out DS-AC1, close the outlet valve and drain the receiver to 0 psi."),

    H1("8. Solvent Parts Washer PW-1"),
    H2("8.1 Solvent and Filter"),
    P("Replace the solvent filter (FE-PW1) monthly. Change the SafeClean 150 solvent every 3 months, or sooner if it is dark "
      "or parts come out oily. Pump spent solvent into the red hazardous waste drum. Follow the PPE in EHS-SOP-001 Section 4.2 "
      "(respirator required for solvent change)."),
    H2("8.2 Fire Lid"),
    P("Quarterly, check the fusible link and lid closure: release the lid prop and confirm the lid falls fully closed. "
      "Replace a fusible link that is painted, corroded or has been exposed to heat (part FL-165, 165 °F rating)."),

    H1("9. Robotic Welding Cell RW-510 (Line 2)"),
    H2("9.1 Torch Consumables"),
    P("Each shift: replace the contact tip (0.045 in / 1.2 mm, part CT-045) and clean spatter from the nozzle with the reamer "
      "station. Every 6 months: replace the wire liner. Enter the cell only with the robot locked out or in teach mode "
      "(EHS-SOP-001 Section 4.2 and 5.3)."),
    H2("9.2 Robot Mechanical"),
    P("Grease all six axis gearboxes with robot grease LUB-RG every 5,000 operating hours, following the robot "
      "manufacturer's purge procedure. After any crash, run the TCP check program P900 before restarting production."),

    H1("10. Troubleshooting Guide"),
    TABLE([
        ["Equipment", "Symptom", "Likely causes", "First actions"],
        ["CV-3", "Belt drifting to one side", "Take-up uneven; material buildup on pulley; worn idler", "Lock out; clean pulleys; adjust tracking (4.2)."],
        ["CV-3", "Bearing hot (above 70 °C) or noisy", "Over- or under-greasing; misalignment; worn bearing", "Check grease history; check alignment; replace bearing if above 80 °C or rough."],
        ["CV-3", "Belt slipping at drive", "Low tension; worn lagging; overload", "Check tension (4.3); inspect lagging."],
        ["HP-400", "Oil temperature above 60 °C", "Cooler fan failed; low water flow; low oil level; relief valve bypassing", "Check fan and water; check level; stop press at 65 °C."],
        ["HP-400", "Press slow or not reaching tonnage", "Low oil; clogged filter; pump wear; relief valve set low", "Check oil and filter indicator; call hydraulic specialist if not resolved."],
        ["HP-400", "Light curtain faults repeatedly", "Dirty lens; misalignment; damaged cable", "Clean lenses; check alignment LEDs; do not run until resolved."],
        ["CNC lathes", "A-102 journal diameter drifting large", "Tool wear; thermal growth (no warm-up); offset error", "Check insert; confirm warm-up ran; adjust wear offset and notify QC."],
        ["CNC lathes", "Poor surface finish", "Worn insert; low coolant concentration; chatter", "Replace insert; check coolant (6.2); check chuck pressure."],
        ["AC-1", "Plant air pressure below 85 psi", "Air leak; intake filter clogged; auto-drain stuck open", "Check filter indicator; check drain; walk the system for leaks."],
        ["RW-510", "Porosity in welds", "Low shielding gas flow; dirty nozzle; drafts", "Check gas flow 35-40 CFH; clean nozzle; check for open doors or fans."],
    ], [0.9, 1.5, 2.0, 2.1]),

    H1("11. Torque Specifications"),
    TABLE([
        ["Application", "Fastener", "Torque"],
        ["HP-400 die clamp bolts", "M20 class 10.9", "250 N·m (184 ft·lb)"],
        ["CV-3 pillow-block bearing mounting bolts", "M16 class 8.8", "190 N·m (140 ft·lb)"],
        ["CV-3 guard fasteners", "M8 class 8.8", "25 N·m (18 ft·lb)"],
        ["CNC chuck jaw bolts", "M12 class 12.9", "110 N·m (81 ft·lb)"],
        ["CNC turret tool holder clamps", "M10 class 12.9", "65 N·m (48 ft·lb)"],
        ["RW-510 torch neck", "Hand tight plus 1/4 turn", "-"],
        ["AC-1 motor mount bolts", "M16 class 8.8", "190 N·m (140 ft·lb)"],
    ], [2.9, 1.8, 1.8]),

    H1("12. Lubricants and Common Spare Parts"),
    TABLE([
        ["Stock code", "Description", "Used on"],
        ["LUB-G2", "NLGI 2 lithium-complex EP grease", "CV-3 bearings, general"],
        ["LUB-G220", "ISO VG 220 synthetic gear oil", "CV-3 gearbox"],
        ["LUB-H46", "ISO VG 46 anti-wear hydraulic oil", "HP-400"],
        ["LUB-W68", "ISO VG 68 way oil", "CNC lathes, HP-400 gibs"],
        ["LUB-C500", "CoolCut 500 semi-synthetic coolant", "CNC lathes"],
        ["LUB-RS8", "Synthetic rotary screw compressor fluid", "AC-1"],
        ["FE-400-10", "HP-400 return filter element, 10 micron", "HP-400"],
        ["FE-AC1-A / FE-AC1-O", "AC-1 intake filter / oil filter", "AC-1"],
        ["FE-PW1", "Parts washer solvent filter", "PW-1"],
        ["CT-045", "MIG contact tip 0.045 in", "RW-510"],
        ["BRG-UCF212", "Flanged pillow-block bearing, 60 mm bore", "CV-3"],
    ], [1.6, 3.0, 1.9]),
    P("Minimum stock: 2 CV-3 bearings, 2 HP-400 filter elements, 1 AC-1 filter kit and 50 contact tips. Reorder from the "
      "storeroom through the CMMS when stock reaches the minimum."),

    H1("13. Work Orders and Records"),
    UL(
        "All PM and corrective work is recorded on a work order in the CMMS. PM work orders are generated automatically from Section 3.",
        "Close work orders within 24 hours of completing the job, recording readings (temperatures, pressures, oil levels), parts used and time spent.",
        "Equipment returned to service after guard removal or LOTO requires the supervisor's sign-off on the work order (EHS-SOP-001 Section 6).",
        "A PM overdue by more than 10% of its interval (for example, 25 hours for a 250-hour task) is escalated to the Maintenance Manager.",
    ),
]

# ====================================================================== QUALITY
QC_META = dict(
    title="Quality Control Standards", doc_no="QC-STD-200", rev="C", effective="2026-02-10",
    owner="Quality Assurance (QA) Manager", approved="QA Manager; Plant Manager",
    applies="Operators, inspectors, floor supervisors and QA staff at Plant 2",
    review="Annually, or when a customer requirement or drawing changes",
    subject="quality control standards", keywords="quality, tolerance, inspection, sampling, AQL, SPC, Cpk, nonconformance, calibration",
)

QC = [
    H1("1. Purpose and Scope"),
    P("This standard defines product specifications, inspection frequencies, sampling plans, measurement requirements and "
      "the handling of nonconforming product for parts made at Plant 2: <b>A-102 Drive Shaft</b> (Line 1), <b>B-220 Mounting "
      "Bracket</b> (Line 2) and <b>C-310 Pump Housing</b> (Line 1). The released customer drawing always governs; if this "
      "standard and the drawing disagree, stop and contact QA."),
    NOTE("Handle machined and stamped parts with cut-resistant gloves (ANSI A2 or higher) as required by EHS-SOP-001 Section 4.2."),

    H1("2. Definitions"),
    TABLE([
        ["Term", "Meaning"],
        ["CTQ", "Critical-to-quality characteristic. Marked with a diamond on the drawing; requires SPC and 100% traceable records."],
        ["FAI", "First-article inspection: full check of the first part(s) after a setup, tooling change or start of shift."],
        ["AQL", "Acceptable quality limit used to choose a sampling plan."],
        ["NCR", "Nonconformance report, recorded in the QMS."],
        ["MRB", "Material Review Board: QA Manager, Production Manager and Product Engineer. Only the MRB may disposition nonconforming product."],
        ["Cpk", "Process capability index: how well a stable process fits within the tolerance, accounting for centering."],
        ["TIR", "Total indicator reading (runout measured with a dial indicator)."],
    ], [1.0, 5.5]),

    H1("3. Part Specifications"),
    H2("3.1 A-102 Drive Shaft (Line 1, CNC-201/202)"),
    P("Material: 4140 steel bar, pre-hardened. Customer drawing A-102 Rev F."),
    TABLE([
        ["Characteristic", "Specification", "CTQ", "Gauge"],
        ["Bearing journal diameter (2 places)", "25.00 mm ±0.02 mm (24.98-25.02)", "Yes", "Micrometer 0-25 / 25-50 mm, 0.001 mm resolution"],
        ["Overall length", "150.0 mm ±0.1 mm", "No", "Height gauge or caliper"],
        ["Keyway width", "8.00 mm +0.03 / -0.00 mm", "Yes", "Go/no-go keyway gauge"],
        ["Keyway depth", "4.0 mm ±0.1 mm", "No", "Depth micrometer"],
        ["Journal runout", "0.02 mm TIR maximum", "Yes", "Dial indicator on V-blocks"],
        ["Journal surface finish", "Ra 0.8 µm maximum", "No", "Surface roughness tester"],
        ["Hardness", "28-32 HRC", "No", "Rockwell hardness tester"],
        ["Chamfers", "0.5 mm x 45° ±0.2 mm, no burrs", "No", "Visual and chamfer gauge"],
    ], [1.9, 1.9, 0.5, 2.2]),
    H2("3.2 B-220 Mounting Bracket (Line 2, HP-400 and RW-510)"),
    P("Material: 4 mm hot-rolled steel, pressed on HP-400 and welded on RW-510. Customer drawing B-220 Rev C."),
    TABLE([
        ["Characteristic", "Specification", "CTQ", "Gauge"],
        ["Mounting hole spacing", "80.0 mm ±0.2 mm", "Yes", "Check fixture CF-220 or caliper"],
        ["Mounting hole diameter", "10.5 mm +0.2 / -0.0 mm", "No", "Pin gauges 10.5 (go) / 10.7 (no-go)"],
        ["Bend angle", "90° ±0.5°", "Yes", "Digital protractor"],
        ["Flatness of mounting face", "0.3 mm maximum", "No", "Feeler gauge on surface plate"],
        ["Weld length (2 fillet welds)", "25 mm minimum each", "Yes", "Weld gauge / ruler"],
        ["Weld size", "4 mm fillet leg minimum", "No", "Fillet weld gauge"],
        ["Weld quality", "No cracks, no incomplete fusion; porosity max 1 mm pore, max 2 pores per weld", "Yes", "Visual (Section 9)"],
    ], [1.9, 1.9, 0.5, 2.2]),
    H2("3.3 C-310 Pump Housing (Line 1, CNC-203)"),
    P("Material: 6061-T6 aluminum casting, machined. Customer drawing C-310 Rev B."),
    TABLE([
        ["Characteristic", "Specification", "CTQ", "Gauge"],
        ["Main bore diameter", "52.000 mm ±0.015 mm", "Yes", "Bore gauge, set with master ring"],
        ["Sealing face flatness", "0.05 mm maximum", "Yes", "CMM"],
        ["Mounting threads (4x)", "M8 x 1.25-6H", "No", "Thread plug gauge go/no-go"],
        ["Bore surface finish", "Ra 1.6 µm maximum", "No", "Surface roughness tester"],
        ["Leak test", "Air at 6 bar (87 psi) for 30 s; max leak 2 cc/min", "Yes", "Leak tester LT-1, 100% of parts"],
    ], [1.9, 1.9, 0.5, 2.2]),

    H1("4. Inspection Plan"),
    H2("4.1 First-Article Inspection (FAI)"),
    P("An FAI of <b>all characteristics</b> in Section 3 is required on the first part after any of the following, and before "
      "production continues:"),
    UL(
        "Start of each shift.",
        "Machine setup or program change.",
        "Tool insert change affecting a CTQ, and any die change on HP-400 (MM-100 Section 5.4).",
        "Machine repair or crash, or return to service after maintenance that touched the machine axes, die or fixtures.",
        "New material lot.",
    ),
    P("The operator measures the part and the floor supervisor or an inspector verifies and signs the FAI record. "
      "Production may not continue until the FAI passes."),
    H2("4.2 In-Process Inspection Frequency"),
    TABLE([
        ["Part", "Characteristic", "Frequency", "Recorded by"],
        ["A-102", "Journal diameter (both)", "Every 25 parts (SPC subgroup of 5 consecutive parts)", "Operator, SPC chart"],
        ["A-102", "Runout and keyway width", "Every 50 parts", "Operator"],
        ["A-102", "Hardness", "Once per material lot", "QC inspector"],
        ["B-220", "Bend angle and hole spacing", "Every 30 parts", "Operator"],
        ["B-220", "Weld visual", "100% of parts", "Operator"],
        ["B-220", "Destructive weld test (cut and etch)", "1 part per shift", "QC inspector"],
        ["C-310", "Bore diameter", "Every 20 parts (SPC subgroup of 5)", "Operator, SPC chart"],
        ["C-310", "Leak test", "100% of parts", "Leak tester LT-1 (automatic record)"],
        ["C-310", "Sealing face flatness (CMM)", "2 parts per shift", "QC inspector"],
    ], [0.7, 1.9, 2.4, 1.5]),
    H2("4.3 Final Inspection"),
    P("Before packing, each lot is sampled per Section 5 for visual defects and the CTQ characteristics. Packing on Line 3 "
      "may not seal a container until the lot has a green QC RELEASED label."),

    H1("5. Sampling Plan for Lot Acceptance"),
    P("Final inspection and incoming inspection of purchased material use the plant's zero-acceptance (c=0) plan below. "
      "<b>Any</b> defect found in the sample rejects the lot: the lot is placed on hold and an NCR is raised (Section 8)."),
    TABLE([
        ["Lot size", "Sample size (non-CTQ characteristics)", "Sample size (CTQ characteristics)", "Accept / reject"],
        ["2-50", "8 (or all if fewer)", "All parts", "Accept 0 / reject 1"],
        ["51-150", "13", "20", "Accept 0 / reject 1"],
        ["151-500", "29", "47", "Accept 0 / reject 1"],
        ["501-1,200", "34", "53", "Accept 0 / reject 1"],
        ["1,201-3,200", "42", "60", "Accept 0 / reject 1"],
        ["3,201-10,000", "50", "74", "Accept 0 / reject 1"],
    ], [1.2, 2.0, 2.0, 1.3]),
    P("Characteristics inspected 100% (C-310 leak test, B-220 weld visual) are not re-sampled; the automatic or operator records are reviewed instead."),

    H1("6. Measuring Equipment and Calibration"),
    TABLE([
        ["Equipment", "Resolution", "Calibration interval", "Daily check"],
        ["Digital calipers", "0.01 mm", "6 months", "Zero check; check against 25 mm gauge block"],
        ["Outside micrometers", "0.001 mm", "6 months", "Zero check with standard"],
        ["Bore gauge", "0.001 mm", "6 months", "Set with 52.000 mm master ring at start of shift"],
        ["Go/no-go gauges and pin gauges", "-", "12 months", "Visual for wear and damage"],
        ["Digital protractor", "0.1°", "12 months", "Check on 90° square"],
        ["CMM", "0.001 mm", "12 months (external)", "Probe qualification on reference sphere"],
        ["Rockwell hardness tester", "0.1 HRC", "12 months (external)", "Test block within ±1.0 HRC of its value"],
        ["Leak tester LT-1", "0.1 cc/min", "12 months", "Master leak part must fail; master good part must pass"],
    ], [1.8, 1.0, 1.5, 2.2]),
    UL(
        "Every gauge carries a green calibration sticker with its ID and due date. <b>Never use a gauge that is past due, damaged or unlabeled.</b>",
        "If a gauge is found out of calibration, quarantine it and notify QA. QA evaluates all product measured with that gauge since its last good calibration.",
        "Gauge R&R for CTQ gauges: under 10% of tolerance is acceptable; 10-30% is conditionally acceptable with QA approval; over 30% is not acceptable.",
        "Personal gauges are not allowed for product acceptance.",
    ),

    H1("7. Statistical Process Control (SPC)"),
    P("CTQ characteristics measured in-process (A-102 journal diameter, C-310 bore diameter) are plotted on X-bar and R charts "
      "using subgroups of 5 consecutive parts. Control limits are recalculated by QA after any process change or every 3 months."),
    H2("7.1 Capability Requirements"),
    UL(
        "Cpk must be at least <b>1.33</b> for every CTQ characteristic in ongoing production.",
        "New or changed processes must show Cpk of at least 1.67 over 30 subgroups before release.",
        "If Cpk falls below 1.33, QA adds 100% inspection of that characteristic until the process is corrected.",
    ),
    H2("7.2 Out-of-Control Rules"),
    P("The process is out of control if any of the following occur on the chart:"),
    OL(
        "One point outside the 3-sigma control limits.",
        "Seven consecutive points on the same side of the center line.",
        "Six consecutive points steadily increasing or decreasing.",
        "Two of three consecutive points beyond the 2-sigma line on the same side.",
    ),
    H2("7.3 Reaction Plan"),
    OL(
        "Stop the process and notify the floor supervisor.",
        "Hold all parts made since the last in-control subgroup and check them 100% for the affected characteristic.",
        "Find and correct the cause (for example tool wear, missed spindle warm-up per MM-100 Section 6.3, or offset error), and note it on the chart.",
        "Run an FAI (Section 4.1) before restarting production.",
    ),
    P("A point outside the control limits is not automatically a nonconforming part. A part is nonconforming only when it is "
      "outside the <b>specification</b> limits in Section 3; then Section 8 also applies."),

    H1("8. Nonconforming Product"),
    H2("8.1 Identify and Segregate"),
    P("Immediately attach a red <b>HOLD</b> tag to any nonconforming or suspect part or container and move it to the red-marked "
      "quarantine cage at the line. Nonconforming parts must never be left at the workstation or mixed with good parts."),
    H2("8.2 Report"),
    P("The floor supervisor or inspector opens an NCR in the QMS <b>within 4 hours</b> of discovery, recording the part number, "
      "lot, quantity, characteristic, measured values and how the problem was found."),
    H2("8.3 Contain"),
    P("Contain all product made since the last good inspection, including parts in work-in-process, finished goods and "
      "the shipping dock. If any suspect product may have shipped, QA must notify the customer <b>within 24 hours</b>."),
    H2("8.4 Disposition"),
    P("Only the MRB may disposition nonconforming product; <b>floor supervisors and operators may not use, rework or scrap held "
      "product on their own</b>. The MRB meets daily at 10:00. Dispositions are:"),
    TABLE([
        ["Disposition", "When used", "Requirements"],
        ["Use as is", "Deviation does not affect form, fit or function", "Engineering approval; customer approval for any CTQ deviation"],
        ["Rework", "Part can be brought into specification", "Approved written rework instruction; 100% re-inspection after rework"],
        ["Scrap", "Part cannot be made conforming", "Mark with red paint, place in scrap bin, record quantity in QMS"],
        ["Return to supplier", "Purchased material defect", "Supplier corrective action request (SCAR) issued by QA"],
    ], [1.4, 2.3, 2.8]),
    H2("8.5 Corrective Action"),
    P("Repeat problems (same defect 3 times in 30 days), customer complaints and any escape to a customer require a formal "
      "corrective action using 8D, with containment within 24 hours and root cause within 10 working days."),

    H1("9. Visual and Workmanship Standards"),
    P("Inspect under at least 1,000 lux lighting at a viewing distance of about 450 mm (18 in), spending about 10 seconds per part surface."),
    TABLE([
        ["Class", "Examples", "Allowed"],
        ["Critical", "Cracks; missing or incomplete welds; wrong part or material; failed leak test", "None. Lot on hold, NCR required."],
        ["Major", "Burrs over 0.2 mm on functional edges or bores; weld porosity over 1 mm; damaged threads; dents on sealing faces", "None in the sample (c=0)."],
        ["Minor", "Light scratches under 0.1 mm deep on non-functional surfaces; minor discoloration; light weld spatter away from mounting faces", "Acceptable. Note trends on the shift log."],
    ], [0.9, 3.7, 1.9]),

    H1("10. Records and Retention"),
    TABLE([
        ["Record", "Retention"],
        ["FAI, in-process and final inspection records", "7 years"],
        ["SPC charts", "7 years"],
        ["NCRs, MRB decisions, corrective actions", "10 years"],
        ["Calibration records", "Life of the gauge plus 3 years"],
        ["Leak test data (C-310)", "10 years (customer requirement)"],
    ], [3.8, 2.7]),

    H1("11. Escalation"),
    TABLE([
        ["Situation", "Escalate to", "Timing"],
        ["Any CTQ out of specification", "Floor supervisor and QA inspector", "Immediately"],
        ["Process out of control (Section 7.2)", "Floor supervisor", "Immediately"],
        ["Suspect product may have shipped", "QA Manager", "Within 1 hour"],
        ["Gauge found out of calibration", "QA", "Before end of shift"],
        ["Quality issue that is also a safety issue (for example a cracked weld on a guard bracket)", "QA Manager and EHS Manager", "Immediately"],
    ], [3.0, 2.0, 1.5]),
]


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    render("safety_procedures.pdf", SAFETY_META, SAFETY)
    render("maintenance_manual.pdf", MAINT_META, MAINT)
    render("quality_control_standards.pdf", QC_META, QC)


if __name__ == "__main__":
    main()
