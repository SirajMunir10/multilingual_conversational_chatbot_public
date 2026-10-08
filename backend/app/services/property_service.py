from typing import List, Dict, Any, Optional, Union
from pydantic import BaseModel, Field
import re
from app.core.audit import AuditService
from app.gateways.inventory_gateway import PropertyInventoryGateway, ScopedPropertyListing
from app.gateways.mortgage_rules_gateway import MortgageRulesGateway
from app.gateways.grid_gateway import GridGateway, GridLeadPayload
from app.services.mortgage_service import MortgageCalculationService, EMIInput
from app.orchestrator.session_store import SessionStore, SessionContext

class PropertySearchFilter(BaseModel):
    city: Optional[str] = None
    location: Optional[str] = None
    type: Optional[str] = None
    budget_min: Optional[float] = None
    budget_max: Optional[float] = None
    beds: Optional[int] = None
    purpose: Optional[str] = None  # buy, rent, invest
    status: Optional[str] = None  # ready, off-plan
    developer: Optional[str] = None
    amenities: Optional[Union[str, List[str]]] = None
    limit: Optional[int] = None

class PropertyMortgageCrossSell(BaseModel):
    property_id: str
    property_price_aed: float
    required_down_payment_pct: float
    required_down_payment_aed: float
    eligible_loan_amount_aed: float
    representative_rate_pct: float
    monthly_emi_aed: float
    tenure_years: int = 25
    disclaimer: str = "estimate only, subject to lender approval"

class PropertyDiscoveryService:
    """
    Phase 4: Property Discovery, Live Inventory Boundary & Recommendation Engine.
    Handles multi-criteria filtering, ranking, conversational refinement,
    shortlisting, and bidirectional mortgage cross-sell (FR-7 to FR-11).
    """

    @classmethod
    def compute_mortgage_cross_sell(
        cls,
        property_item: ScopedPropertyListing,
        nationality: str = "expat",
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        FR-11: Cross-sell calculation for property interest.
        Computes statutory down payment and monthly EMI using best available partner bank rates.
        """
        is_national = "national" in nationality.lower()
        # UAE Central Bank LTV limits:
        # Properties <= 5M AED: 80% LTV for expats (20% down), 85% for nationals (15% down)
        # Properties > 5M AED: 75% LTV for expats (25% down), 80% for nationals (20% down)
        if is_national:
            max_ltv = 85.0 if property_item.price <= 5000000.0 else 80.0
        else:
            max_ltv = 80.0 if property_item.price <= 5000000.0 else 75.0

        down_payment_pct = 100.0 - max_ltv
        down_payment_aed = round(property_item.price * (down_payment_pct / 100.0), 2)
        loan_amount_aed = round(property_item.price - down_payment_aed, 2)

        # Retrieve best partner bank rate from MortgageRulesGateway
        best_rate = 4.29  # Default to best available profit rate (DIB Murabaha)
        best_product_info = {
            "product_id": "dib_murabaha_fixed_3yr",
            "bank_name": "Dubai Islamic Bank",
            "rate": 4.29,
            "finance_type": "islamic"
        }
        products = MortgageRulesGateway.get_mortgage_products(session_id=session_id)
        if products:
            best_prod = min(products, key=lambda p: p.interest_rate)
            best_rate = best_prod.interest_rate
            best_product_info = {
                "product_id": best_prod.product_id,
                "bank_name": best_prod.bank_name,
                "rate": best_prod.interest_rate,
                "finance_type": best_prod.finance_type
            }

        # Deterministic EMI calculation
        emi_res = MortgageCalculationService.calc_emi(
            EMIInput(
                loan_amount=loan_amount_aed,
                interest_rate=best_rate,
                tenure=25,
                frequency="monthly"
            ),
            session_id=session_id
        )

        return {
            "property_id": property_item.id,
            "property_price_aed": property_item.price,
            "down_payment_pct": down_payment_pct,
            "down_payment_aed": down_payment_aed,
            "required_down_payment_pct": down_payment_pct,
            "required_down_payment_aed": down_payment_aed,
            "loan_amount_aed": loan_amount_aed,
            "eligible_loan_amount_aed": loan_amount_aed,
            "representative_rate_pct": best_rate,
            "estimated_monthly_emi_aed": emi_res["periodic_installment_aed"],
            "monthly_emi_aed": emi_res["periodic_installment_aed"],
            "recommended_product": best_product_info,
            "tenure_years": 25,
            "label": "estimates, not offers",
            "disclaimer": "estimate only, subject to lender approval"
        }

    @classmethod
    def search_and_rank(
        cls,
        filters: PropertySearchFilter,
        nationality: str = "expat",
        session_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        FR-8: Query live inventory gateway and return 3-5 ranked matches enriched with cross-sell math.
        """
        target_city = filters.city or filters.location
        listings = PropertyInventoryGateway.search_properties(
            city=target_city,
            type=filters.type,
            budget_min=filters.budget_min,
            budget_max=filters.budget_max,
            beds=filters.beds,
            purpose=filters.purpose,
            status=filters.status,
            developer=filters.developer,
            amenities=filters.amenities,
            limit=filters.limit,
            session_id=session_id
        )

        # Tolerant fallback 1: if exact budget cap returned 0 results, expand budget buffer by 20%
        if not listings and filters.budget_max:
            listings = PropertyInventoryGateway.search_properties(
                city=target_city,
                type=filters.type,
                budget_min=filters.budget_min,
                budget_max=filters.budget_max * 1.20,
                beds=filters.beds,
                purpose=filters.purpose,
                status=filters.status,
                developer=filters.developer,
                amenities=filters.amenities,
                limit=filters.limit,
                session_id=session_id
            )

        # Tolerant fallback 2: if still 0 and type was specified, relax type in that community
        if not listings and target_city and filters.type:
            listings = PropertyInventoryGateway.search_properties(
                city=target_city,
                type=None,
                budget_min=filters.budget_min,
                budget_max=(filters.budget_max * 1.20) if filters.budget_max else None,
                beds=filters.beds,
                purpose=filters.purpose,
                status=filters.status,
                developer=filters.developer,
                amenities=filters.amenities,
                limit=filters.limit,
                session_id=session_id
            )

        # Note: Do not silently broaden community to all Dubai here, as that bypasses FR-8 Smart Catalog Fallbacks.
        # Fallback recommendations are handled conversationally via find_catalog_alternatives().

        # Check session shortlist to set active heart state
        shortlisted_ids = set()
        if session_id:
            sess = SessionStore.get_session(session_id)
            if sess:
                shortlisted_ids = set(sess.shortlisted_properties)

        enriched_results = []
        for prop in listings:
            data = prop.model_dump()
            data["mortgage_cross_sell"] = cls.compute_mortgage_cross_sell(prop, nationality, session_id)
            data["is_shortlisted"] = prop.id in shortlisted_ids
            enriched_results.append(data)

        # Save to session context as last recommended
        if session_id:
            sess = SessionStore.get_session(session_id)
            if sess:
                sess.last_recommended_properties = enriched_results
                # Update slots
                if target_city: sess.slots.property_city = target_city
                if filters.type: sess.slots.property_type = filters.type
                if filters.budget_max: sess.slots.property_budget_max = filters.budget_max
                if filters.budget_min: sess.slots.property_budget_min = filters.budget_min
                if filters.beds: sess.slots.property_beds = filters.beds
                if filters.purpose: sess.slots.property_purpose = filters.purpose

        return enriched_results

    @classmethod
    def refine_search(
        cls,
        first_arg: Any,
        second_arg: Optional[str] = None,
        nationality: str = "expat",
        **kwargs
    ) -> Any:
        """
        FR-9: Conversational Refinement Handler.
        Supports both:
        1. Object-based: refine_search(filter_obj: PropertySearchFilter, instruction: str) -> PropertySearchFilter
        2. Session-based: refine_search(session_id: str, refinement_text: str, nationality: str) -> Dict[str, Any]
        """
        # Branch 1: Object-based refinement for direct filter manipulation
        if isinstance(first_arg, PropertySearchFilter):
            filt = first_arg.model_copy()
            text_lower = (second_arg or "").lower()

            if any(w in text_lower for w in ["cheaper", "less expensive", "lower budget", "too expensive", "affordable"]):
                curr_max = filt.budget_max or 3000000.0
                filt.budget_max = curr_max * 0.80
            elif any(w in text_lower for w in ["luxury", "higher budget", "more expensive", "premium"]):
                filt.budget_max = (filt.budget_max or 2500000.0) * 1.50

            if any(w in text_lower for w in ["more bedroom", "larger", "bigger", "extra bed"]):
                filt.beds = min((filt.beds or 2) + 1, 5)
            elif any(w in text_lower for w in ["fewer bedroom", "smaller", "1 bed", "studio"]):
                filt.beds = max((filt.beds or 2) - 1, 1)

            if "downtown" in text_lower:
                filt.location = "Downtown Dubai"
                filt.city = "Downtown Dubai"
            elif "business bay" in text_lower:
                filt.location = "Business Bay"
                filt.city = "Business Bay"
            elif "marina" in text_lower:
                filt.location = "Dubai Marina"
                filt.city = "Dubai Marina"
            elif "palm" in text_lower:
                filt.location = "Palm Jumeirah"
                filt.city = "Palm Jumeirah"

            if any(w in text_lower for w in ["metro", "مترو", "मेट्रो"]):
                filt.amenities = "metro"

            return filt

        # Branch 2: Session-based refinement (for router and orchestrator)
        session_id = first_arg
        refinement_text = second_arg or kwargs.get("refinement_text", "")
        sess = SessionStore.get_or_create_session(session_id)
        text_lower = refinement_text.lower()
        refinement_action = "filter_update"

        # 1. Check for "more like #X" or "similar to #X"
        match_index = re.search(r'(?:like|similar to|about)\s+#?(\d+)', text_lower)
        if match_index and sess.last_recommended_properties:
            idx = int(match_index.group(1)) - 1
            if 0 <= idx < len(sess.last_recommended_properties):
                ref_prop = sess.last_recommended_properties[idx]
                similar_props = PropertyInventoryGateway.get_similar_properties(ref_prop["id"], limit=4, session_id=session_id)
                enriched = []
                for p in similar_props:
                    d = p.model_dump()
                    d["mortgage_cross_sell"] = cls.compute_mortgage_cross_sell(p, nationality, session_id)
                    d["is_shortlisted"] = p.id in set(sess.shortlisted_properties)
                    enriched.append(d)
                sess.last_recommended_properties = enriched
                return {
                    "action": "similar_properties",
                    "reference_property": ref_prop["title"],
                    "results_count": len(enriched),
                    "properties": enriched
                }

        # 2. Check for "cheaper" / "budget lower"
        if any(w in text_lower for w in ["cheaper", "less expensive", "lower budget", "too expensive", "affordable"]):
            current_max = sess.slots.property_budget_max
            if not current_max and sess.last_recommended_properties:
                current_max = max(p["price"] for p in sess.last_recommended_properties)
            if current_max:
                sess.slots.property_budget_max = current_max * 0.80
                refinement_action = "lowered_budget"

        # 3. Check for "more expensive" / "luxury"
        elif any(w in text_lower for w in ["luxury", "higher budget", "more expensive", "premium"]):
            current_max = sess.slots.property_budget_max or 2500000.0
            sess.slots.property_budget_max = current_max * 1.50
            refinement_action = "increased_budget"

        # 4. Check for bedroom adjustments
        if any(w in text_lower for w in ["more bedroom", "larger", "bigger", "extra bed"]):
            curr_beds = sess.slots.property_beds or 2
            sess.slots.property_beds = min(curr_beds + 1, 5)
            refinement_action = "increased_beds"
        elif any(w in text_lower for w in ["fewer bedroom", "smaller", "1 bed", "studio"]):
            curr_beds = sess.slots.property_beds or 2
            sess.slots.property_beds = max(curr_beds - 1, 1)
            refinement_action = "decreased_beds"

        # 5. Check for community / location shifts
        for comm in ["downtown", "marina", "business bay", "palm", "hills", "jvc", "creek", "ranches", "yas"]:
            if comm in text_lower:
                sess.slots.property_city = comm
                refinement_action = f"location_shifted_to_{comm}"
                break

        # 6. Check for amenity requirements (metro, pool, gym, balcony, beach)
        if any(w in text_lower for w in ["metro", "مترو", "मेट्रो"]):
            sess.slots.property_amenities = ["Near Metro Station"]
            refinement_action = "filtered_by_metro"
        elif "pool" in text_lower or "مسبح" in text_lower:
            sess.slots.property_amenities = ["Pool"]
            refinement_action = "filtered_by_pool"
        elif "gym" in text_lower or "جيم" in text_lower:
            sess.slots.property_amenities = ["Gym"]
            refinement_action = "filtered_by_gym"
        elif "balcony" in text_lower or "شرفة" in text_lower:
            sess.slots.property_amenities = ["Balcony"]
            refinement_action = "filtered_by_balcony"
        elif any(w in text_lower for w in ["beach", "sea view"]):
            sess.slots.property_amenities = ["Beach Access"]
            refinement_action = "filtered_by_beach"

        # Re-execute search with updated slots
        filters = PropertySearchFilter(
            city=sess.slots.property_city,
            type=sess.slots.property_type,
            budget_min=sess.slots.property_budget_min,
            budget_max=sess.slots.property_budget_max,
            beds=sess.slots.property_beds,
            purpose=sess.slots.property_purpose,
            amenities=sess.slots.property_amenities or None
        )
        updated_results = cls.search_and_rank(filters, nationality=nationality, session_id=session_id)

        return {
            "action": refinement_action,
            "filters_applied": filters.model_dump(),
            "results_count": len(updated_results),
            "properties": updated_results
        }

    @classmethod
    def shortlist_property(
        cls,
        arg1: Optional[str] = None,
        arg2: Optional[str] = None,
        user_id: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        FR-10: Save / shortlist property from chat.
        Flexible argument handling:
        - shortlist_property(property_id, session_id=..., user_id=...)
        - shortlist_property(session_id, property_id, user_id=...)
        """
        session_id = kwargs.get("session_id")
        property_id = kwargs.get("property_id")
        user_id = user_id or kwargs.get("user_id")

        if arg1:
            if arg1.startswith("prop-") or arg1.startswith("prop_"):
                property_id = property_id or arg1
                session_id = session_id or (arg2 if arg2 else "default_session")
            elif arg2 and (arg2.startswith("prop-") or arg2.startswith("prop_")):
                property_id = property_id or arg2
                session_id = session_id or arg1
            else:
                session_id = session_id or arg1
                property_id = property_id or arg2

        session_id = session_id or "default_session"
        if not property_id:
            return {"success": False, "error": "Property ID is required."}

        sess = SessionStore.get_or_create_session(session_id, user_id=user_id)
        prop = PropertyInventoryGateway.get_property_by_id(property_id, session_id=session_id)
        if not prop:
            return {"success": False, "error": f"Property '{property_id}' not found."}

        # Toggle or add
        is_already_saved = property_id in sess.shortlisted_properties
        if is_already_saved:
            sess.shortlisted_properties.remove(property_id)
            status_text = "removed"
        else:
            sess.shortlisted_properties.append(property_id)
            status_text = "saved"

        AuditService.log_event(
            event_type="business_write",
            action="shortlist_property",
            resource="property_shortlist",
            session_id=session_id,
            user_id=user_id,
            details={
                "property_id": property_id,
                "status": status_text,
                "total_shortlisted": len(sess.shortlisted_properties),
                "is_authenticated": user_id is not None
            }
        )

        # If anonymous user and saving property, require lead capture so their list is not lost
        requires_lead_capture = (user_id is None) and (status_text == "saved")

        return {
            "success": True,
            "status": status_text,
            "is_shortlisted": status_text == "saved",
            "property_id": property_id,
            "property_title": prop.title,
            "total_shortlisted": len(sess.shortlisted_properties),
            "requires_lead_capture": requires_lead_capture,
            "lead_capture_prompt": "Save your shortlist! Enter your email or WhatsApp to receive property brochures and private viewing availability." if requires_lead_capture else None
        }

    @classmethod
    def get_shortlist(cls, session_id: str = "default_session", user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Retrieve full listings for all currently shortlisted properties in session.
        """
        sess = SessionStore.get_or_create_session(session_id, user_id=user_id)
        results = []
        for pid in sess.shortlisted_properties:
            prop = PropertyInventoryGateway.get_property_by_id(pid, session_id=session_id)
            if prop:
                d = prop.model_dump()
                d["mortgage_cross_sell"] = cls.compute_mortgage_cross_sell(prop, session_id=session_id)
                d["is_shortlisted"] = True
                results.append(d)
        return results

    @classmethod
    def get_user_shortlist(cls, session_id: str = "default_session", user_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """Alias for get_shortlist."""
        return cls.get_shortlist(session_id=session_id, user_id=user_id)

    @classmethod
    def clear_shortlists(cls) -> None:
        """Clear all active session shortlists (used in tests)."""
        for s in SessionStore._sessions.values():
            s.shortlisted_properties.clear()

    @classmethod
    def capture_anonymous_lead(
        cls,
        session_id: str = "default_session",
        name: Optional[str] = None,
        email: Optional[str] = None,
        phone: Optional[str] = None,
        notes: Optional[str] = None,
        property_id: Optional[str] = None,
        full_name: Optional[str] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        FR-10: Convert anonymous shortlisted session into a CRM lead in Grid.
        """
        c_name = name or full_name or kwargs.get("full_name") or kwargs.get("contact_name") or "Interested Client"
        c_email = email or kwargs.get("email") or kwargs.get("contact_email") or ""
        c_phone = phone or kwargs.get("phone") or kwargs.get("contact_phone") or ""
        sess_id = session_id or kwargs.get("session_id") or "default_session"
        prop_id = property_id or kwargs.get("property_id")

        sess = SessionStore.get_or_create_session(sess_id)
        shortlist = sess.shortlisted_properties
        target_prop = prop_id or (shortlist[0] if shortlist else "portfolio_shortlist")

        # Create lead in Grid CRM Gateway
        lead_req = GridLeadPayload(
            contact_name=c_name,
            contact_email=c_email,
            contact_phone=c_phone,
            property_id=target_prop,
            inquiry_type="shortlist_portfolio",
            notes=f"Source: chat_anonymous_shortlist | Session: {sess_id} | Property: {target_prop} | Notes: {notes or 'User requested shortlist brochures'}"
        )
        grid_lead = GridGateway.create_lead(lead_req, session_id=sess_id)

        # Mark user_id on session
        sess.user_id = c_email

        AuditService.log_event(
            event_type="business_write",
            action="capture_shortlist_lead",
            resource="grid_crm",
            session_id=sess_id,
            details={
                "lead_id": grid_lead.lead_id,
                "property_id": target_prop,
                "shortlisted_count": len(shortlist),
                "properties": shortlist
            }
        )

        return {
            "status": "success",
            "success": True,
            "lead_id": grid_lead.lead_id,
            "property_id": target_prop,
            "message": f"Your shortlist has been saved! A member of our luxury advisory team will email you the brochures shortly.",
            "shortlisted_count": len(shortlist)
        }

    @classmethod
    def compare_displayed_properties(
        cls,
        properties: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        FR-9 Multi-Turn Refinement & Comparison:
        Analyzes and contrasts properties currently displayed on screen.
        Computes metric comparisons (price/sqft, monthly EMI, entry cost, community yields).
        """
        if not properties:
            return {"count": 0, "properties": [], "analysis_points": []}

        items = []
        for p in properties:
            sq_ft = p.get("sq_ft") or 1000
            price = p.get("price") or 0.0
            pps = round(price / sq_ft, 2)
            cross_sell = p.get("mortgage_cross_sell") or {}
            emi = cross_sell.get("monthly_emi_aed") or cross_sell.get("estimated_monthly_emi_aed") or 0.0
            down = cross_sell.get("down_payment_aed") or round(price * 0.20, 2)
            
            # Community benchmark estimated gross rental yield
            comm = (p.get("community") or "").lower()
            if "business bay" in comm or "jvc" in comm:
                est_yield = "6.8% – 7.4%"
            elif "dubai hills" in comm:
                est_yield = "6.5% – 7.0%"
            elif "marina" in comm or "creek" in comm:
                est_yield = "6.2% – 6.8%"
            elif "palm" in comm or "downtown" in comm:
                est_yield = "5.4% – 6.2% (with high capital appreciation)"
            else:
                est_yield = "6.0% – 6.5%"

            items.append({
                "id": p.get("id"),
                "title": p.get("title"),
                "community": p.get("community"),
                "beds": p.get("beds"),
                "sq_ft": sq_ft,
                "price": price,
                "price_per_sq_ft": pps,
                "down_payment_aed": down,
                "monthly_emi_aed": emi,
                "estimated_rental_yield": est_yield,
                "developer": p.get("developer"),
                "status": p.get("status")
            })

        analysis = []
        if len(items) >= 2:
            cheapest = min(items, key=lambda x: x["price"])
            largest = max(items, key=lambda x: x["sq_ft"])
            best_value = min(items, key=lambda x: x["price_per_sq_ft"])
            analysis.append(f"Lowest capital outlay: {cheapest['title']} at AED {cheapest['price']:,.0f} (EMI: ~AED {cheapest['monthly_emi_aed']:,.0f}/mo).")
            analysis.append(f"Most expansive layout: {largest['title']} with {largest['sq_ft']} sq.ft.")
            analysis.append(f"Best value per sq.ft: {best_value['title']} at AED {best_value['price_per_sq_ft']:,.0f}/sq.ft.")

        return {
            "count": len(items),
            "properties": items,
            "analysis_points": analysis
        }

    @classmethod
    def find_catalog_alternatives(
        cls,
        filters: PropertySearchFilter
    ) -> Dict[str, Any]:
        """
        FR-8 Smart Catalog & Fallback Recommendations:
        Inspects catalog when exact criteria yields 0 results.
        Proactively discovers:
        1. Alternative bedroom tiers & property types available in the requested community.
        2. Alternative communities in the catalog with the user's desired bedroom count.
        """
        all_props = PropertyInventoryGateway.get_all_properties()
        target_comm = (filters.city or filters.location or "").lower().strip()
        target_beds = filters.beds
        req_type = filters.type.lower() if filters.type else None

        # 1. Properties within the requested community/location
        comm_props = []
        if target_comm:
            if target_comm in ["uae", "all uae", "all", "united arab emirates", "anywhere in uae", "anywhere"]:
                comm_props = list(all_props)
            elif target_comm in ["dubai", "all dubai", "dxb"]:
                comm_props = [p for p in all_props if "dubai" in p.city.lower()]
            elif target_comm in ["abu dhabi", "all abu dhabi", "auh"]:
                comm_props = [p for p in all_props if "abu dhabi" in p.city.lower()]
            else:
                comm_props = [
                    p for p in all_props
                    if target_comm in p.community.lower() or target_comm in p.city.lower()
                ]

        # Group same-community properties by bedroom count and property type
        bed_tiers_map = {}
        for p in comm_props:
            if target_beds is not None and p.beds == target_beds and req_type and req_type not in p.type.lower():
                # Same beds but different type (e.g. townhouse instead of apartment)
                key = (p.beds, p.type)
            elif target_beds is not None and p.beds == target_beds:
                # Same beds in this community (zero match must be due to budget/amenity)
                key = (p.beds, p.type)
            else:
                key = (p.beds, p.type)

            if key not in bed_tiers_map:
                bed_tiers_map[key] = []
            bed_tiers_map[key].append(p)

        available_beds_in_community = []
        for (b, t), props_list in sorted(bed_tiers_map.items(), key=lambda x: (x[0][0], min(p.price for p in x[1]))):
            min_price = min(p.price for p in props_list)
            sample_prop = min(props_list, key=lambda p: p.price)
            available_beds_in_community.append({
                "beds": b,
                "type": t,
                "count": len(props_list),
                "starting_price_aed": min_price,
                "sample_title": sample_prop.title,
                "property_id": sample_prop.id
            })

        # Same community alternative property models (sorted by price ascending)
        same_comm_other_beds = sorted(
            [p for p in comm_props if target_beds is None or p.beds != target_beds or (filters.budget_max and p.price > filters.budget_max)],
            key=lambda x: x.price
        )

        # 2. Alternative communities matching the requested bedroom count
        other_comm_same_beds_map = {}
        if target_beds is not None:
            matching_bed_props = [
                p for p in all_props
                if p.beds == target_beds
                and (not target_comm or (target_comm not in p.community.lower() and target_comm not in p.city.lower()))
            ]
            for p in matching_bed_props:
                comm = p.community
                if comm not in other_comm_same_beds_map:
                    other_comm_same_beds_map[comm] = []
                other_comm_same_beds_map[comm].append(p)

        other_communities_summary = []
        for comm, props_list in other_comm_same_beds_map.items():
            min_price = min(p.price for p in props_list)
            sample_prop = min(props_list, key=lambda p: p.price)
            other_communities_summary.append({
                "community": comm,
                "beds": target_beds,
                "count": len(props_list),
                "starting_price_aed": min_price,
                "sample_title": sample_prop.title,
                "property_id": sample_prop.id
            })
        other_communities_summary.sort(key=lambda x: x["starting_price_aed"])

        other_comm_same_beds = []
        for comm_info in other_communities_summary:
            other_comm_same_beds.extend(other_comm_same_beds_map[comm_info["community"]])

        return {
            "target_community": filters.city or filters.location or "Dubai",
            "requested_beds": target_beds,
            "has_same_comm_alternatives": len(same_comm_other_beds) > 0,
            "has_community_properties": len(comm_props) > 0,
            "available_beds_in_community": available_beds_in_community,
            "same_community_alternatives": [p.model_dump() for p in same_comm_other_beds[:4]],
            "has_other_comm_alternatives": len(other_comm_same_beds) > 0,
            "other_communities_summary": other_communities_summary[:4],
            "other_community_alternatives": [p.model_dump() for p in other_comm_same_beds[:4]]
        }
