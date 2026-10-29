"""
Stage 3: Filter

Applies quality and relevance gates:
- Drops the exact seed
- Drops generic 1-word head terms
- Drops near-duplicates (high token overlap)
- Selectively filters brand terms while keeping comparison queries
- Drops off-topic or gibberish phrases
- Logs every discarded candidate with reason for debugging
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from keyword_analysis.config import Config
from keyword_analysis.stages.enrich import EnrichedKeyword
from keyword_analysis.utils.logger import get_logger
from keyword_analysis.utils.normalizer import jaccard_similarity, normalize

log = get_logger(__name__)

# Canonical set of legitimate short words (≤2 chars) that are NOT junk
SAFE_SHORT_WORDS = {
    "to", "in", "by", "of", "on", "at", "up", "if", "as", "is", "it",
    "my", "ai", "ui", "no", "do", "go", "me", "we", "he", "an", "or", "am",
    "so", "us", "be", "ok", "tv", "hr", "vs", "uk", "3d", "2d",
}


def has_junk_letter(text: str) -> bool:
    """
    Returns True if the keyword text contains a standalone single or
    two-character word that is NOT in the known safe set.
    This catches autocomplete alphabet-sweep artifacts like:
      'g interior design', 'interior designer h', 'af ai services'
    """
    words = text.lower().split()
    for w in words:
        if len(w) <= 2 and w not in SAFE_SHORT_WORDS:
            return True
    return False


# Location indicators, Indian cities/states, and global tech hubs
LOCATION_TERMS = {
    # Local intent phrases
    "near me", "nearby", "near by", "around me", "in my area", "close to me", "locally",
    # Major Indian Cities & Tech Hubs (including common spelling variations)
    "noida", "greater noida", "bengaluru", "beghluru", "bengluru", "bangalore", "banglore",
    "pune", "delhi", "new delhi", "mumbai", "bombay", "hyderabad", "chennai", "madras",
    "kolkata", "calcutta", "gurgaon", "gurugram", "jaipur", "ahmedabad", "chandigarh",
    "indore", "lucknow", "kochi", "cochin", "coimbatore", "bhopal", "nagpur", "patna",
    "surat", "vadodara", "ghaziabad", "faridabad", "thane", "navi mumbai", "visakhapatnam",
    "vizag", "ludhiana", "agra", "nashik", "meerut", "varanasi", "srinagar", "aurangabad",
    "amritsar", "allahabad", "prayagraj", "ranchi", "gwalior", "jabalpur", "jodhpur",
    "raipur", "kota", "guwahati", "dehradun", "mysore", "mysuru", "mangalore", "mangaluru",
    "trivandrum", "thiruvananthapuram", "kozhikode", "calicut", "goa", "mohali",
    "panchkula", "secunderabad", "kalyan", "vasai", "virar", "bareilly", "aligarh",
    "moradabad", "jalandhar", "bhubaneswar", "salem", "warangal", "guntur", "kannur",
    "tiruppur", "trichy", "tiruchirappalli", "hubli", "belgaum", "dhanbad", "shimla",
    "pondicherry", "puducherry", "ncr", "delhi ncr",
    # Indian States
    "maharashtra", "karnataka", "tamil nadu", "telangana", "uttar pradesh", "gujarat",
    "rajasthan", "kerala", "punjab", "haryana", "bihar", "west bengal", "madhya pradesh",
    "andhra pradesh", "odisha", "assam", "himachal", "uttarakhand",
}

# Strictly forbidden international countries, foreign cities, and regions
INTERNATIONAL_LOCATIONS = {
    # Countries
    "usa", "us", "united states", "america", "uk", "united kingdom", "britain", "england", "scotland", "wales",
    "canada", "australia", "germany", "france", "italy", "spain", "netherlands", "sweden", "norway", "denmark",
    "finland", "russia", "china", "japan", "korea", "south korea", "singapore", "malaysia", "indonesia",
    "thailand", "vietnam", "philippines", "dubai", "uae", "united arab emirates", "saudi", "saudi arabia",
    "qatar", "kuwait", "oman", "bahrain", "egypt", "south africa", "nigeria", "kenya", "brazil", "argentina",
    "mexico", "chile", "colombia", "new zealand", "ireland", "switzerland", "austria", "belgium", "poland",
    "portugal", "greece", "turkey", "israel", "pakistan", "bangladesh", "sri lanka", "nepal", "bhutan", "myanmar",
    # Global Major Cities
    "london", "manchester", "birmingham", "new york", "los angeles", "chicago", "houston", "phoenix",
    "philadelphia", "san antonio", "san diego", "dallas", "san jose", "austin", "seattle", "san francisco",
    "boston", "toronto", "vancouver", "montreal", "sydney", "melbourne", "brisbane", "perth", "berlin",
    "munich", "frankfurt", "paris", "tokyo", "beijing", "shanghai", "hong kong", "bangkok", "hanoi",
    "ho chi minh", "jakarta", "kuala lumpur", "manila", "taipei", "seoul", "amsterdam", "brussels",
    "madrid", "barcelona", "rome", "milan", "zurich", "geneva", "vienna", "auckland", "lahore", "karachi",
    "islamabad", "dhaka", "colombo", "kathmandu",
    # Continents & Regions
    "europe", "european", "asia", "asian", "north america", "south america", "africa", "middle east",
}

# Permitted domestic locations for a company in Mumbai, Maharashtra, India
ALLOWED_DOMESTIC_LOCATIONS = {
    "india", "indian", "maharashtra", "mumbai", "bombay",
}

# All known location terms to check against
ALL_KNOWN_LOCATIONS = LOCATION_TERMS | INTERNATIONAL_LOCATIONS

def has_disallowed_location(text: str) -> bool:
    """
    Strictly validates location for a company based in Mumbai, Maharashtra, India.
    - All international locations are strictly blocked.
    - Any Indian city/state NOT in Mumbai, Maharashtra, or India is blocked.
    """
    norm = text.lower()
    
    # 1. Block local intent phrases like 'near me'
    if re.search(r"\b(near me|nearby|near by|around me|in my area|close to me)\b", norm):
        return True

    # 2. Check for any mention of a known location (Domestic or International)
    # If it's a known location term but NOT in our whitelist, block it.
    
    # Check multi-word locations first (e.g., 'new york', 'new delhi')
    for loc in ALL_KNOWN_LOCATIONS:
        if " " in loc:
            if re.search(rf"\b{re.escape(loc)}\b", norm):
                # If the multi-word location is not allowed, block it
                is_allowed = False
                for allowed in ALLOWED_DOMESTIC_LOCATIONS:
                    if allowed in loc:
                        is_allowed = True
                        break
                if not is_allowed:
                    return True

    # Check single-word tokens
    tokens = set(re.findall(r"\b[a-z]+\b", norm))
    for token in tokens:
        if token in ALL_KNOWN_LOCATIONS:
            if token not in ALLOWED_DOMESTIC_LOCATIONS:
                return True
                
    # 3. Aggressive 'in [word]' check for unknown cities
    # If we see 'in [something]' and [something] is not in our allowed list, 
    # and it's not a common stop word, block it.
    matches = re.findall(r"\bin ([a-z]+)\b", norm)
    for place in matches:
        if place not in ALLOWED_DOMESTIC_LOCATIONS and place not in SAFE_SHORT_WORDS:
            # Common English words that might follow 'in' in a keyword context
            common_in_words = {"our", "the", "your", "a", "an", "this", "that", "business", "services", "design", "development"}
            if place not in common_in_words:
                return True

    return False


def has_location(text: str) -> bool:
    """Legacy helper maintained for backward compatibility."""
    return has_disallowed_location(text)


def is_irrelevant_noise(text: str, seed: str = "") -> bool:
    """
    Detects irrelevant media/entertainment, job postings, or nonsense collocations
    when the seed topic does not explicitly ask for them.
    Examples: 'backend song', 'fly with backend', 'backend jobs near me'
    """
    norm = text.lower()
    seed_lower = (seed or "").lower()

    # 1. Songs/music/movies unless seed is music-related
    media_words = ["song", "songs", "lyrics", "mp3", "video song", "ringtone", "album", "soundtrack", "movie"]
    if not any(mw in seed_lower for mw in media_words):
        for mw in media_words:
            if re.search(rf"\b{re.escape(mw)}\b", norm):
                return True

    # 2. Job vacancies / hiring / salaries unless seed is job-related
    job_words = ["jobs", "job", "vacancy", "vacancies", "salary", "salaries", "hiring", "recruitment", "walkin", "walk in"]
    if not any(jw in seed_lower for jw in job_words):
        for jw in job_words:
            if re.search(rf"\b{re.escape(jw)}\b", norm):
                return True
    # 3. Administrative / Legal / Compliance junk (HSN, GST, etc.)
    admin_words = ["hsn code", "sac code", "gst rate", "gst registration", "tax rate", "hsn", "sac", "registration", "gst"]
    if not any(aw in seed_lower for aw in admin_words):
        for aw in admin_words:
            if re.search(rf"\b{re.escape(aw)}\b", norm):
                return True

    # 4. Known irrelevant collocations or nonsense
    if re.search(r"\bfly with\b", norm):
        return True

    return False


# Common brand names or platforms that might appear
COMMON_BRANDS = {
    "ikea", "livspace", "homelane", "urban ladder", "pepperfry", "urban company",
    "houzz", "pinterest", "instagram", "youtube", "amazon", "flipkart",
    "fiverr", "upwork", "freelancer", "justdial", "sulekha", "zenon",
    "alberto pinto", "kelly wearstler", "martyn lawrence bullard", "jean louis deniot",
}


def has_disallowed_brand(text: str, seed: str = "") -> bool:
    norm = text.lower()
    seed_lower = (seed or "").lower()
    words = set(re.findall(r"\b[a-z0-9]+\b", norm))
    for brand in COMMON_BRANDS:
        if brand not in seed_lower:
            if " " in brand and brand in norm:
                return True
            if " " not in brand and brand in words:
                return True
    return False


def is_safe_top_keyword(text: str, seed: str = "") -> bool:
    """
    Strict validator for Top 5 recommended keywords.
    Ensures:
    - No single-letter junk artifacts ('g interior design', 'c interior design')
    - No location-based keywords ('in noida', 'pune', 'bengaluru', 'near me')
    - No irrelevant songs, jobs, or nonsense collocations ('backend song', 'fly with backend')
    - No off-topic / hijacking brand names ('zenon iot services')
    """
    if has_junk_letter(text):
        return False
    if has_location(text):
        return False
    if is_irrelevant_noise(text, seed):
        return False
    if has_disallowed_brand(text, seed):
        return False
    return True


@dataclass
class DiscardedKeyword:
    text: str
    reason: str
    stage: str = "filter"


class FilterStage:
    def __init__(self, config: Config):
        self.cfg = config
        self.brand_blocklist = set(config.filter.brand_blocklist) | COMMON_BRANDS

    def _is_comparison_query(self, text: str) -> bool:
        """Keep brand if it's part of a comparative/alternative search."""
        return bool(re.search(r"\b(vs|versus|alternative|alternatives|like|compared to|or)\b", text))

    def _contains_disallowed_brand(self, text: str) -> bool:
        words = text.split()
        for brand in self.brand_blocklist:
            if brand in text:
                # If it's a comparison query, keep it!
                if self._is_comparison_query(text):
                    return False
                return True
        return False

    def _is_junk(self, text: str) -> bool:
        # Too many numbers or special patterns
        if re.search(r"\b\d{4,}\b", text):  # 4+ digit numbers
            return True
        # Check repeated characters like "aaaa"
        if re.search(r"(.)\1{3,}", text):
            return True
        
        # AGGRESSIVE ARTIFACT FILTER: use the centralized check
        if has_junk_letter(text):
            return True

        # Block specific technical nonsense words mentioned by user
        norm = text.lower()
        if norm in ["gcc", "http", "https", "www", "com", "hsn", "sac", "gst"]:
            return True
            
        # Block HSN/SAC code mentions anywhere in junk check too
        if re.search(r"\b(hsn|sac|gst|tax|code)\b", norm):
            # Only allow 'code' if it's not administrative (e.g., 'qr code' is fine, but not 'hsn code')
            if "hsn" in norm or "sac" in norm or "gst" in norm:
                return True
                
        return False

    def run(
        self, keywords: List[EnrichedKeyword], seed: str
    ) -> Tuple[List[EnrichedKeyword], List[DiscardedKeyword]]:
        norm_seed = normalize(seed)
        log.info("=== Starting Stage 3: Filter (%d candidates) ===", len(keywords))

        survivors: List[EnrichedKeyword] = []
        discarded: List[DiscardedKeyword] = []

        # Sort by unique sources descending, then similarity descending
        # so near-duplicate filtering keeps the stronger candidate
        sorted_keywords = sorted(
            keywords,
            key=lambda k: (k.unique_sources, k.similarity_to_seed, -k.distance),
            reverse=True,
        )

        kept_canonical_texts: List[str] = []

        for kw in sorted_keywords:
            text = kw.text

            # 1. Drop exact seed
            if text == norm_seed:
                discarded.append(DiscardedKeyword(text=text, reason="exact_seed"))
                continue

            # 2. Word count bounds
            if kw.word_count < self.cfg.filter.min_word_count:
                # Allow single word ONLY if it has strong intent modifier (rare)
                discarded.append(DiscardedKeyword(text=text, reason="generic_head_term_too_short"))
                continue

            if kw.word_count > self.cfg.filter.max_word_count:
                discarded.append(DiscardedKeyword(text=text, reason="phrase_too_long"))
                continue

            # 3. Relevance gate
            if kw.similarity_to_seed < self.cfg.thresholds.keep_threshold:
                discarded.append(
                    DiscardedKeyword(
                        text=text,
                        reason=f"similarity_below_keep_threshold ({kw.similarity_to_seed:.2f} < {self.cfg.thresholds.keep_threshold:.2f})",
                    )
                )
                continue

            # 4. Brand check
            if self._contains_disallowed_brand(text):
                discarded.append(DiscardedKeyword(text=text, reason="brand_without_comparison"))
                continue

            # 5. Strict safety check (Locations, Junk, Brands, etc.)
            if not is_safe_top_keyword(text, seed):
                discarded.append(DiscardedKeyword(text=text, reason="failed_strict_safety_check"))
                continue

            # 6. Near-duplicate suppression
            is_near_dup = False
            for kept in kept_canonical_texts:
                if jaccard_similarity(text, kept) >= self.cfg.filter.near_duplicate_threshold:
                    discarded.append(
                        DiscardedKeyword(
                            text=text,
                            reason=f"near_duplicate_of '{kept}' (jaccard >= {self.cfg.filter.near_duplicate_threshold})",
                        )
                    )
                    is_near_dup = True
                    break

            if is_near_dup:
                continue

            # All checks passed!
            survivors.append(kw)
            kept_canonical_texts.append(text)

        log.info(
            "Stage 3 complete: %d keywords kept, %d discarded",
            len(survivors),
            len(discarded),
        )
        return survivors, discarded
