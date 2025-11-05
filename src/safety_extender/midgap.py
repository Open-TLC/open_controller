close_pairs: List[Dict[str, Any]] = []
    for i in range(len(enriched) - 1):
        back = enriched[i]
        front = enriched[i + 1]
        if (front > 100) and (front < 40 ):
            widen_veh = i
            gap = round(front["dist"] - back["dist"], 2)

        
        if gap < threshold_m:
            close_pairs.append({
                "back_id": back.get("sumo_id"),
                "front_id": front.get("sumo_id"),
                "back_dist_m": back["dist"],
                "front_dist_m": front["dist"],
                "gap_m": gap,
            })