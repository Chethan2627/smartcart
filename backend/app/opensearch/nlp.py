"""
Natural-Language Search Query Parser for SmartCart 2.0.
Extracts price constraints, availability preferences, and sorting intents
from user natural-language queries without requiring external LLM dependencies.
"""
from dataclasses import dataclass
import re
from typing import Optional, Tuple


@dataclass
class ParsedNLPQuery:
    """Structured representation of extracted natural language search parameters."""
    clean_query: str
    min_price_paise: Optional[int] = None
    max_price_paise: Optional[int] = None
    in_stock_only: Optional[bool] = None
    sort_by: Optional[str] = None
    extracted_intents: Optional[dict] = None


class NaturalLanguageSearchParser:
    """
    Rule-based natural language parser for e-commerce search queries.
    Parses conversational phrases like:
    - 'show wireless headphones under 3000'
    - 'cheap running shoes between 500 and 1500'
    - 'premium organic milk in stock'
    """

    # Price pattern with optional currency symbol and k suffix (e.g., 3k, rs. 500, ₹2,000)
    _NUM = r"(?:₹|rs\.?|inr)?\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*(k)?"

    # Range pattern: "between X and Y" or "from X to Y" or "X to Y"
    _RANGE_REGEX = re.compile(
        rf"\b(?:between|from)\s+{_NUM}\s+(?:and|to|-)\s+{_NUM}\b",
        re.IGNORECASE,
    )
    _DASH_RANGE_REGEX = re.compile(
        rf"\b{_NUM}\s*(?:-|to)\s*{_NUM}\b",
        re.IGNORECASE,
    )

    # Max price: "under X", "below X", "less than X", "upto X", "max X", "<= X", "< X"
    _MAX_PRICE_REGEX = re.compile(
        rf"\b(?:under|below|less\s+than|upto|up\s+to|max|maximum|at\s+most|<=?)\s+{_NUM}\b",
        re.IGNORECASE,
    )

    # Min price: "above X", "over X", "more than X", "greater than X", "min X", ">= X", "> X"
    _MIN_PRICE_REGEX = re.compile(
        rf"\b(?:above|over|more\s+than|greater\s+than|min|minimum|at\s+least|>=?)\s+{_NUM}\b",
        re.IGNORECASE,
    )

    # In-stock intent
    _IN_STOCK_REGEX = re.compile(
        r"\b(?:in\s+stock|available|in-stock|ready\s+to\s+ship|available\s+now)\b",
        re.IGNORECASE,
    )

    # Sort intents
    _CHEAP_SORT_REGEX = re.compile(
        r"\b(?:cheap|cheapest|affordable|budget|low\s+price|lowest\s+price)\b",
        re.IGNORECASE,
    )
    _PREMIUM_SORT_REGEX = re.compile(
        r"\b(?:expensive|most\s+expensive|premium|luxury|high\s+end|highest\s+price)\b",
        re.IGNORECASE,
    )
    _NEWEST_SORT_REGEX = re.compile(
        r"\b(?:latest|newest|new\s+arrivals?)\b",
        re.IGNORECASE,
    )

    # Conversational filler words
    _FILLER_REGEX = re.compile(
        r"\b(?:show\s+me|show|find\s+me|find|search\s+for|search|looking\s+for|look\s+for|i\s+want|get\s+me|give\s+me|products?|items?|please)\b",
        re.IGNORECASE,
    )

    @classmethod
    def _parse_amount(cls, num_str: str, k_flag: Optional[str]) -> int:
        """Convert parsed numeric string and optional 'k' multiplier into integer paise."""
        cleaned = num_str.replace(",", "").strip()
        val = float(cleaned)
        if k_flag and k_flag.lower() == "k":
            val *= 1000
        # Convert rupees to paise (1 Rupee = 100 Paise)
        return int(round(val * 100))

    @classmethod
    def parse(cls, query: Optional[str]) -> ParsedNLPQuery:
        """Parse natural language query and extract structured search parameters."""
        if not query or not query.strip():
            return ParsedNLPQuery(clean_query="", extracted_intents={})

        text = query.strip()
        extracted: dict = {}
        min_price: Optional[int] = None
        max_price: Optional[int] = None
        in_stock: Optional[bool] = None
        sort_by: Optional[str] = None

        # 1. Check price range: "between X and Y"
        range_match = cls._RANGE_REGEX.search(text)
        if not range_match:
            range_match = cls._DASH_RANGE_REGEX.search(text)

        if range_match:
            n1_str, k1, n2_str, k2 = range_match.groups()
            try:
                p1 = cls._parse_amount(n1_str, k1)
                p2 = cls._parse_amount(n2_str, k2)
                min_price = min(p1, p2)
                max_price = max(p1, p2)
                extracted["price_range"] = (min_price, max_price)
                text = text[:range_match.start()] + " " + text[range_match.end():]
            except Exception:
                pass
        else:
            # 2. Check max price
            max_match = cls._MAX_PRICE_REGEX.search(text)
            if max_match:
                n_str, k = max_match.groups()
                try:
                    max_price = cls._parse_amount(n_str, k)
                    extracted["max_price"] = max_price
                    text = text[:max_match.start()] + " " + text[max_match.end():]
                except Exception:
                    pass

            # 3. Check min price
            min_match = cls._MIN_PRICE_REGEX.search(text)
            if min_match:
                n_str, k = min_match.groups()
                try:
                    min_price = cls._parse_amount(n_str, k)
                    extracted["min_price"] = min_price
                    text = text[:min_match.start()] + " " + text[min_match.end():]
                except Exception:
                    pass

        # 4. Check stock availability intent
        if cls._IN_STOCK_REGEX.search(text):
            in_stock = True
            extracted["in_stock_only"] = True
            text = cls._IN_STOCK_REGEX.sub(" ", text)

        # 5. Check sort intents
        if cls._CHEAP_SORT_REGEX.search(text):
            sort_by = "price_asc"
            extracted["sort_by"] = "price_asc"
            text = cls._CHEAP_SORT_REGEX.sub(" ", text)
        elif cls._PREMIUM_SORT_REGEX.search(text):
            sort_by = "price_desc"
            extracted["sort_by"] = "price_desc"
            text = cls._PREMIUM_SORT_REGEX.sub(" ", text)
        elif cls._NEWEST_SORT_REGEX.search(text):
            sort_by = "newest"
            extracted["sort_by"] = "newest"
            text = cls._NEWEST_SORT_REGEX.sub(" ", text)

        # 6. Remove conversational filler words
        text = cls._FILLER_REGEX.sub(" ", text)

        # 7. Normalize residual whitespace
        clean_text = re.sub(r"\s+", " ", text).strip()

        return ParsedNLPQuery(
            clean_query=clean_text,
            min_price_paise=min_price,
            max_price_paise=max_price,
            in_stock_only=in_stock,
            sort_by=sort_by,
            extracted_intents=extracted,
        )
