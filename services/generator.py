"""
AppraisAI — Report Generator Service
======================================
Wraps the appraisal generation logic so it can be called dynamically
from the backend with a dict of parameters (instead of hardcoded variables).

Drop your generate_appraisal.py logic below the DATA SECTION marker.
The generate_report() function replaces all the top-level DATA variables
with the kwargs passed in from claude_service.py.
"""

import io
import os
import sys
import tempfile
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# ── Ensure python-docx + Pillow are available ──
try:
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement
except ImportError:
    os.system("pip install python-docx --break-system-packages -q")
    from docx import Document
    from docx.shared import Inches, Pt, RGBColor, Cm
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from docx.enum.table import WD_TABLE_ALIGNMENT
    from docx.oxml.ns import qn
    from docx.oxml import OxmlElement

try:
    from PIL import Image, ImageDraw, ImageFont
except ImportError:
    os.system("pip install Pillow --break-system-packages -q")
    from PIL import Image, ImageDraw, ImageFont


DEFAULT_ASSUMPTIONS = [
    "No responsibility is assumed for matters legal in character or nature. Title to the property is assumed to be good and marketable.",
    "The property is appraised free and clear of any or all liens or encumbrances unless otherwise stated.",
    "Responsible ownership and competent property management are assumed.",
    "The information furnished by others is believed to be reliable; however, no warranty is given for its accuracy.",
    "All engineering studies are assumed to be correct. Any plot plans and illustrative material in this report are included only to help the reader visualize the property.",
    "It is assumed that there are no hidden or unapparent conditions of the property, subsoil, or structures that render it more or less valuable.",
    "It is assumed that the property is in full compliance with all applicable federal, state, and local environmental regulations and laws unless otherwise stated.",
    "It is assumed that the property conforms to all applicable zoning and use regulations and restrictions unless a nonconformity has been identified, described, and considered.",
    "It is assumed that all required licenses, certificates of occupancy, consents, and other legislative or administrative authority have been or can be obtained.",
    "It is assumed that the use of the land and improvements is confined within the boundaries or property lines of the property described and that there is no encroachment or trespass unless otherwise stated.",
    "The appraiser is not qualified to detect hazardous waste and/or toxic materials. Any comment by the appraiser that might suggest the possibility of the presence of such substances should not be taken as confirmation.",
    "This appraisal report has been made in conformity with the Uniform Standards of Professional Appraisal Practice (USPAP) as adopted by the Appraisal Standards Board of The Appraisal Foundation.",
    "The appraiser has not been asked to act, and is not acting, as an advocate for any party to this transaction.",
    "Any distribution of the total valuation between land and improvements applies only under the stated program of utilization.",
    "This appraisal was generated with AI assistance through the AppraisAI platform. All AI-derived data and analysis have been reviewed and verified by the signing Certified General Appraiser, who takes full professional responsibility for the conclusions herein.",
]


def generate_report(
    # ── Property Identification ──
    property_address: str, city: str, state: str, zip_code: str,
    county: str = "", municipality: str = "", block_lot: str = "",
    census_tract: str = "", tax_map: str = "",
    # ── Property Characteristics ──
    property_type: str = "", improvement_type: str = "",
    year_built: str = "", year_renovated: str = "", stories: int = 1,
    gba: str = "", nra: str = "", site_sf: str = "", site_acres: str = "",
    parking: str = "", occupancy: str = "", condition: str = "Good",
    zoning: str = "", far: str = "",
    flood_zone: str = "Zone X (Minimal Flood Hazard)", flood_panel: str = "",
    # ── Construction ──
    foundation: str = "", structure: str = "", roof: str = "",
    hvac: str = "", electrical: str = "", plumbing: str = "",
    interior: str = "", exterior_walls: str = "",
    # ── Valuation ──
    concluded_value: str = "", concluded_value_words: str = "",
    value_per_sf: str = "", effective_date: str = "",
    inspection_date: str = "", report_date: str = "",
    interest_appraised: str = "Fee Simple",
    report_type: str = "Appraisal Report",
    intended_use: str = "mortgage underwriting and internal decision-making",
    sales_comp_value: str = "", income_value: str = "", cost_value: str = "",
    cap_rate: str = "", noi: str = "", grm: str = "N/A", egim: str = "",
    # ── Client / Appraiser ──
    client_name: str = "[Client Name]", client_org: str = "[Client Organization]",
    client_address: str = "[Client Address]",
    appraiser_name: str = "[Appraiser Name, MAI]",
    appraiser_license: str = "[State Certified General Appraiser — License #XXXXX]",
    appraiser_firm: str = "AppraisAI Appraiser Network",
    # ── Complex data ──
    comparable_sales: list = None, income_data: dict = None,
    regional_analysis: str = "", neighborhood_analysis: str = "",
    site_description: str = "", improvement_description: str = "",
    highest_best_use_vacant: str = "", highest_best_use_improved: str = "",
    assumptions_and_conditions: list = None,
    # ── Output ──
    output_path: str = None,
) -> bytes:
    """
    Build a USPAP-compliant appraisal .docx and return the raw bytes.
    If output_path is provided, also write to disk.
    """

    if comparable_sales is None:
        comparable_sales = []
    if income_data is None:
        income_data = {}
    if assumptions_and_conditions is None:
        assumptions_and_conditions = DEFAULT_ASSUMPTIONS
    if not effective_date:
        effective_date = datetime.now().strftime("%B %-d, %Y")
    if not report_date:
        report_date = effective_date

    # ── Bind all variables so the template body below can reference them ──
    PROPERTY_ADDRESS     = property_address
    CITY                 = city
    STATE                = state
    ZIP                  = zip_code
    COUNTY               = county
    MUNICIPALITY         = municipality
    BLOCK_LOT            = block_lot
    CENSUS_TRACT         = census_tract
    TAX_MAP              = tax_map
    PROPERTY_TYPE        = property_type
    IMPROVEMENT_TYPE     = improvement_type
    YEAR_BUILT           = year_built
    YEAR_RENOVATED       = year_renovated
    STORIES              = stories
    GBA                  = gba
    NRA                  = nra
    SITE_SF              = site_sf
    SITE_ACRES           = site_acres
    PARKING              = parking
    OCCUPANCY            = occupancy
    CONDITION            = condition
    ZONING               = zoning
    FAR                  = far
    FLOOD_ZONE           = flood_zone
    FLOOD_PANEL          = flood_panel
    FOUNDATION           = foundation
    STRUCTURE            = structure
    ROOF                 = roof
    HVAC                 = hvac
    ELECTRICAL           = electrical
    PLUMBING             = plumbing
    INTERIOR             = interior
    EXTERIOR_WALLS       = exterior_walls
    CONCLUDED_VALUE      = concluded_value
    CONCLUDED_VALUE_WORDS= concluded_value_words
    VALUE_PER_SF         = value_per_sf
    EFFECTIVE_DATE       = effective_date
    INSPECTION_DATE      = inspection_date
    REPORT_DATE          = report_date
    INTEREST_APPRAISED   = interest_appraised
    REPORT_TYPE          = report_type
    INTENDED_USE         = intended_use
    SALES_COMP_VALUE     = sales_comp_value
    INCOME_VALUE         = income_value
    COST_VALUE           = cost_value
    CAP_RATE             = cap_rate
    NOI                  = noi
    GRM                  = grm
    EGIM                 = egim
    CLIENT_NAME          = client_name
    CLIENT_ORG           = client_org
    CLIENT_ADDRESS       = client_address
    APPRAISER_NAME       = appraiser_name
    APPRAISER_LICENSE    = appraiser_license
    APPRAISER_FIRM       = appraiser_firm
    COMPARABLE_SALES     = comparable_sales
    INCOME_DATA          = income_data
    REGIONAL_ANALYSIS    = regional_analysis
    NEIGHBORHOOD_ANALYSIS= neighborhood_analysis
    SITE_DESCRIPTION     = site_description
    IMPROVEMENT_DESCRIPTION       = improvement_description
    HIGHEST_BEST_USE_VACANT       = highest_best_use_vacant
    HIGHEST_BEST_USE_IMPROVED     = highest_best_use_improved
    ASSUMPTIONS_AND_CONDITIONS    = assumptions_and_conditions

    # ══════════════════════════════════════════════════════════════════════
    #  REPORT BUILDER — paste the report-building code from
    #  generate_appraisal.py here (everything AFTER the DATA SECTION).
    #  Replace the OUTPUT_PATH write at the end with the buffer approach below.
    # ══════════════════════════════════════════════════════════════════════

    # Import the original script as a module to avoid duplicating all the
    # formatting logic. We patch its globals with our local variables first.
    import importlib.util, pathlib

    script_path = pathlib.Path(__file__).parent.parent / "generate_appraisal_core.py"

    if script_path.exists():
        spec = importlib.util.spec_from_file_location("core", script_path)
        core = importlib.util.module_from_spec(spec)
        # Inject our variables into the module's namespace
        for var_name, var_val in {
            "PROPERTY_ADDRESS": PROPERTY_ADDRESS, "CITY": CITY, "STATE": STATE,
            "ZIP": ZIP, "COUNTY": COUNTY, "MUNICIPALITY": MUNICIPALITY,
            "BLOCK_LOT": BLOCK_LOT, "CENSUS_TRACT": CENSUS_TRACT,
            "TAX_MAP": TAX_MAP, "PROPERTY_TYPE": PROPERTY_TYPE,
            "IMPROVEMENT_TYPE": IMPROVEMENT_TYPE, "YEAR_BUILT": YEAR_BUILT,
            "YEAR_RENOVATED": YEAR_RENOVATED, "STORIES": STORIES,
            "GBA": GBA, "NRA": NRA, "SITE_SF": SITE_SF, "SITE_ACRES": SITE_ACRES,
            "PARKING": PARKING, "OCCUPANCY": OCCUPANCY, "CONDITION": CONDITION,
            "ZONING": ZONING, "FAR": FAR, "FLOOD_ZONE": FLOOD_ZONE,
            "FLOOD_PANEL": FLOOD_PANEL, "FOUNDATION": FOUNDATION,
            "STRUCTURE": STRUCTURE, "ROOF": ROOF, "HVAC": HVAC,
            "ELECTRICAL": ELECTRICAL, "PLUMBING": PLUMBING,
            "INTERIOR": INTERIOR, "EXTERIOR_WALLS": EXTERIOR_WALLS,
            "CONCLUDED_VALUE": CONCLUDED_VALUE,
            "CONCLUDED_VALUE_WORDS": CONCLUDED_VALUE_WORDS,
            "VALUE_PER_SF": VALUE_PER_SF, "EFFECTIVE_DATE": EFFECTIVE_DATE,
            "INSPECTION_DATE": INSPECTION_DATE, "REPORT_DATE": REPORT_DATE,
            "INTEREST_APPRAISED": INTEREST_APPRAISED, "REPORT_TYPE": REPORT_TYPE,
            "INTENDED_USE": INTENDED_USE, "SALES_COMP_VALUE": SALES_COMP_VALUE,
            "INCOME_VALUE": INCOME_VALUE, "COST_VALUE": COST_VALUE,
            "CAP_RATE": CAP_RATE, "NOI": NOI, "GRM": GRM, "EGIM": EGIM,
            "CLIENT_NAME": CLIENT_NAME, "CLIENT_ORG": CLIENT_ORG,
            "CLIENT_ADDRESS": CLIENT_ADDRESS, "APPRAISER_NAME": APPRAISER_NAME,
            "APPRAISER_LICENSE": APPRAISER_LICENSE, "APPRAISER_FIRM": APPRAISER_FIRM,
            "COMPARABLE_SALES": COMPARABLE_SALES, "INCOME_DATA": INCOME_DATA,
            "REGIONAL_ANALYSIS": REGIONAL_ANALYSIS,
            "NEIGHBORHOOD_ANALYSIS": NEIGHBORHOOD_ANALYSIS,
            "SITE_DESCRIPTION": SITE_DESCRIPTION,
            "IMPROVEMENT_DESCRIPTION": IMPROVEMENT_DESCRIPTION,
            "HIGHEST_BEST_USE_VACANT": HIGHEST_BEST_USE_VACANT,
            "HIGHEST_BEST_USE_IMPROVED": HIGHEST_BEST_USE_IMPROVED,
            "ASSUMPTIONS_AND_CONDITIONS": ASSUMPTIONS_AND_CONDITIONS,
            "OUTPUT_PATH": output_path or "/tmp/_appraisai_out.docx",
        }.items():
            setattr(core, var_name, var_val)
        spec.loader.exec_module(core)
        docx_path = output_path or "/tmp/_appraisai_out.docx"
    else:
        raise FileNotFoundError(
            "generate_appraisal_core.py not found. "
            "Copy your generate_appraisal.py to appraisai-backend/generate_appraisal_core.py "
            "and remove the DATA SECTION at the top."
        )

    with open(docx_path, "rb") as f:
        return f.read()
