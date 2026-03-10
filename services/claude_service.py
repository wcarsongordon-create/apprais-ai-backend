"""
AppraisAI — Claude API Service
================================
Calls the Anthropic API to research a property and return structured
JSON data, which is then passed to the report generator.
"""

import json
import os
import time
import logging
from typing import Optional, List
from anthropic import Anthropic

logger = logging.getLogger(__name__)
client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


RESEARCH_SYSTEM_PROMPT = """You are a senior commercial real estate research analyst for AppraisAI.
Your job is to research a property and return structured data for a USPAP-compliant appraisal report.

You must return ONLY a valid JSON object — no markdown, no explanation, no preamble.
Use your knowledge of commercial real estate markets, property databases, and local market conditions.
When specific data is unavailable, provide reasonable market-based estimates and mark them with
"(est.)" in the value string. The reviewing appraiser will verify all data before certifying.

Be thorough, professional, and accurate. All dollar values should be formatted as strings like "$1,250,000".
All percentages as strings like "7.50%". Numeric fields (like STORIES) as integers."""


def build_research_prompt(
    address: str, city: str, state: str, zip_code: str, property_type: str,
    purpose: str, estimated_value: str, gba: str, year_built: str
) -> str:
    return f"""Research this commercial property for an appraisal report and return a complete JSON object.

SUBJECT PROPERTY:
  Address: {address}
  City/State/ZIP: {city}, {state} {zip_code}
  Property Type: {property_type}
  Purpose of Appraisal: {purpose}
  Estimated Value Range: {estimated_value or "Unknown"}
  Reported GBA: {gba or "Unknown"}
  Reported Year Built: {year_built or "Unknown"}

Return a JSON object with EXACTLY this structure (fill in all fields):

{{
  "property": {{
    "address": "{address}",
    "city": "{city}",
    "state": "{state}",
    "zip": "{zip_code}",
    "county": "<county name>",
    "municipality": "<municipality>",
    "block_lot": "<parcel ID or block/lot if known, else '(est.) — verify via county assessor'>",
    "census_tract": "<census tract number>",
    "tax_map": "<tax map reference>",
    "property_type": "{property_type}",
    "improvement_type": "<specific description, e.g. 'Two-Story Class B Office Building'>",
    "year_built": "<year built>",
    "year_renovated": "<year renovated or 'No major renovation noted'>",
    "stories": <integer number of stories>,
    "gba": "<gross building area in SF, formatted with commas>",
    "nra": "<net rentable area in SF>",
    "site_sf": "<site area in SF>",
    "site_acres": "<site area in acres>",
    "parking": "<parking description>",
    "occupancy": "<current occupancy status>",
    "condition": "<Good / Average / Fair>",
    "zoning": "<zoning designation and description>",
    "far": "<floor area ratio>",
    "flood_zone": "<FEMA flood zone designation>",
    "flood_panel": "<FEMA panel number>",
    "foundation": "<foundation type>",
    "structure": "<structural system>",
    "roof": "<roof type and condition>",
    "hvac": "<HVAC system description>",
    "electrical": "<electrical service description>",
    "plumbing": "<plumbing description>",
    "interior": "<interior description>",
    "exterior_walls": "<exterior wall description>"
  }},
  "valuation": {{
    "concluded_value": "<dollar amount, e.g. '$1,250,000'>",
    "concluded_value_words": "<value spelled out in ALL CAPS, e.g. 'ONE MILLION TWO HUNDRED FIFTY THOUSAND DOLLARS'>",
    "value_per_sf": "<value per SF of GBA>",
    "effective_date": "<today's date formatted as 'Month D, YYYY'>",
    "inspection_date": "<today's date>",
    "report_date": "<today's date>",
    "interest_appraised": "Fee Simple",
    "sales_comp_value": "<sales comparison approach indicated value>",
    "income_value": "<income capitalization approach indicated value>",
    "cost_value": "<cost approach indicated value>",
    "cap_rate": "<capitalization rate used, e.g. '7.50%'>",
    "noi": "<net operating income, e.g. '$85,000'>",
    "egim": "<effective gross income multiplier>"
  }},
  "income": {{
    "pgi": "<potential gross income>",
    "vacancy_rate": "<vacancy rate %>",
    "vacancy_loss": "<vacancy loss $>",
    "egi": "<effective gross income>",
    "taxes": "<real estate taxes>",
    "insurance": "<insurance expense>",
    "maintenance": "<maintenance & repairs>",
    "management": "<management fee>",
    "reserves": "<capital reserves>",
    "total_expenses": "<total operating expenses>",
    "noi": "<net operating income>",
    "expense_ratio": "<expense ratio %>"
  }},
  "comparables": [
    {{
      "num": 1,
      "address": "<full address of comparable sale>",
      "sale_price": "<sale price>",
      "sale_date": "<Month YYYY>",
      "property_type": "<property type>",
      "gba": "<GBA in SF>",
      "site_sf": "<site SF>",
      "price_per_sf": "<price per SF>",
      "year_built": "<year built>",
      "stories": <integer>,
      "condition": "<condition>",
      "location_adj": "<adjustment % e.g. '+3%' or '-5%' or '0%'>",
      "size_adj": "<adjustment %>",
      "condition_adj": "<adjustment %>",
      "age_adj": "<adjustment %>",
      "net_adj": "<net adjustment %>",
      "adjusted_price": "<adjusted sale price>"
    }},
    {{ ... comp 2 ... }},
    {{ ... comp 3 ... }},
    {{ ... comp 4 ... }}
  ],
  "narratives": {{
    "regional_analysis": "<3-paragraph narrative about the metro area economy, demographics, major employers, and real estate market trends>",
    "neighborhood_analysis": "<2-paragraph narrative about the immediate neighborhood, nearby uses, traffic, transit, and development trends>",
    "site_description": "<1-2 paragraph narrative describing the site dimensions, topography, utilities, access, and any notable features>",
    "improvement_description": "<2-3 paragraph narrative describing the building in detail: layout, construction, systems, condition>",
    "hbu_vacant": "<1 paragraph highest and best use analysis as if vacant>",
    "hbu_improved": "<1 paragraph highest and best use analysis as improved>"
  }}
}}"""



def _build_document_section(document_texts: list) -> str:
    """Build the client-documents block appended to the research prompt."""
    if not document_texts:
        return ""
    lines = [
        "\n\n## CLIENT-PROVIDED DOCUMENTS",
        "The following financial documents were uploaded by the client.",
        "Use this actual data to inform the Income Approach: NOI, vacancy,",
        "operating expenses, cap rates, and income/expense summaries.",
        "Where actual figures are available, prefer them over market estimates.\n",
    ]
    income_docs  = [d for d in document_texts if d.get("doc_type") == "income"]
    expense_docs = [d for d in document_texts if d.get("doc_type") == "expenses"]
    other_docs   = [d for d in document_texts if d.get("doc_type") not in ("income", "expenses")]

    def _add_group(title, docs):
        if not docs:
            return
        lines.append(f"### {title}")
        for doc in docs:
            lines.append(f"\n--- {doc['filename']} ---")
            lines.append(doc.get("text", "[no text extracted]"))

    _add_group("Income Statements & Leases", income_docs)
    _add_group("Expense Documents", expense_docs)
    _add_group("Other Documents", other_docs)
    return "\n".join(lines)



async def research_property(
    address: str, city: str, state: str, zip_code: str,
    property_type: str, purpose: str,
    estimated_value: str = "", gba: str = "", year_built: str = "",
    document_texts: Optional[list] = None
) -> dict:
    """
    Call Claude to research a property and return structured JSON data
    ready to be passed to the report generator.
    """
    start = time.time()
    logger.info(f"Starting Claude research for {address}, {city} {state}")

    prompt = build_research_prompt(
        address, city, state, zip_code, property_type,
        purpose, estimated_value, gba, year_built
    )
    if document_texts:
        prompt += _build_document_section(document_texts)

    response = client.messages.create(
        model="claude-opus-4-5-20251101",
        max_tokens=8000,
        system=RESEARCH_SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = response.content[0].text.strip()

    # Strip markdown code fences if Claude added them
    if raw.startswith("```"):
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]
    raw = raw.strip()

    data = json.loads(raw)

    elapsed = int(time.time() - start)
    logger.info(f"Claude research complete in {elapsed}s for {address}")
    data["_meta"] = {"generation_seconds": elapsed, "model": "claude-opus-4-5-20251101"}

    return data


def extract_generation_params(research_data: dict) -> dict:
    """
    Flatten the research_data JSON into the flat keyword-argument dict
    that generate_report() in generator.py expects.
    """
    p  = research_data.get("property",   {})
    v  = research_data.get("valuation",  {})
    i  = research_data.get("income",     {})
    n  = research_data.get("narratives", {})
    comps = research_data.get("comparables", [])

    return dict(
        # ── Property Identification ──
        property_address   = p.get("address", ""),
        city               = p.get("city", ""),
        state              = p.get("state", ""),
        zip_code           = p.get("zip", ""),
        county             = p.get("county", ""),
        municipality       = p.get("municipality", ""),
        block_lot          = p.get("block_lot", ""),
        census_tract       = p.get("census_tract", ""),
        tax_map            = p.get("tax_map", ""),

        # ── Property Characteristics ──
        property_type      = p.get("property_type", ""),
        improvement_type   = p.get("improvement_type", ""),
        year_built         = p.get("year_built", ""),
        year_renovated     = p.get("year_renovated", ""),
        stories            = p.get("stories", 1),
        gba                = p.get("gba", ""),
        nra                = p.get("nra", ""),
        site_sf            = p.get("site_sf", ""),
        site_acres         = p.get("site_acres", ""),
        parking            = p.get("parking", ""),
        occupancy          = p.get("occupancy", ""),
        condition          = p.get("condition", ""),
        zoning             = p.get("zoning", ""),
        far                = p.get("far", ""),
        flood_zone         = p.get("flood_zone", ""),
        flood_panel        = p.get("flood_panel", ""),

        # ── Construction ──
        foundation         = p.get("foundation", ""),
        structure          = p.get("structure", ""),
        roof               = p.get("roof", ""),
        hvac               = p.get("hvac", ""),
        electrical         = p.get("electrical", ""),
        plumbing           = p.get("plumbing", ""),
        interior           = p.get("interior", ""),
        exterior_walls     = p.get("exterior_walls", ""),

        # ── Valuation ──
        concluded_value       = v.get("concluded_value", ""),
        concluded_value_words = v.get("concluded_value_words", ""),
        value_per_sf          = v.get("value_per_sf", ""),
        effective_date        = v.get("effective_date", ""),
        inspection_date       = v.get("inspection_date", ""),
        report_date           = v.get("report_date", ""),
        interest_appraised    = v.get("interest_appraised", "Fee Simple"),
        sales_comp_value      = v.get("sales_comp_value", ""),
        income_value          = v.get("income_value", ""),
        cost_value            = v.get("cost_value", ""),
        cap_rate              = v.get("cap_rate", ""),
        noi                   = v.get("noi", ""),
        egim                  = v.get("egim", ""),

        # ── Income Data ──
        income_data = dict(
            pgi           = i.get("pgi", ""),
            vacancy_rate  = i.get("vacancy_rate", ""),
            vacancy_loss  = i.get("vacancy_loss", ""),
            egi           = i.get("egi", ""),
            taxes         = i.get("taxes", ""),
            insurance     = i.get("insurance", ""),
            maintenance   = i.get("maintenance", ""),
            management    = i.get("management", ""),
            reserves      = i.get("reserves", ""),
            total_expenses= i.get("total_expenses", ""),
            noi           = i.get("noi", ""),
            expense_ratio = i.get("expense_ratio", ""),
        ),

        # ── Comparables ──
        comparable_sales = comps,

        # ── Narratives ──
        regional_analysis       = n.get("regional_analysis", ""),
        neighborhood_analysis   = n.get("neighborhood_analysis", ""),
        site_description        = n.get("site_description", ""),
        improvement_description = n.get("improvement_description", ""),
        highest_best_use_vacant   = n.get("hbu_vacant", ""),
        highest_best_use_improved = n.get("hbu_improved", ""),
    )

