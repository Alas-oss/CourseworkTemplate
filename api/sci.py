def _round(value):
    return round(value, 6)


def calculate_sci(profiles, functional_units=None):
    if not profiles:
        raise ValueError("No carbon profiles selected")

    names = {p["functional_unit_name"] for p in profiles}

    if functional_units is None:
        units = {p["functional_unit"] for p in profiles}

        if len(units) > 1 or len(names) > 1:
            raise ValueError(
                "Selected services use different functional units; "
                "send functional_units to use one value for all"
            )

        r = units.pop()
    else:
        r = functional_units

    unit_name = names.pop() if len(names) == 1 else "unit"

    lines = []
    energy = 0.0
    operational = 0.0
    embodied = 0.0

    for p in profiles:
        op = p["energy_kwh"] * p["carbon_intensity_gco2e_per_kwh"]
        emb = p["embodied_emissions_gco2e"]

        energy += p["energy_kwh"]
        operational += op
        embodied += emb

        lines.append({
            "service_name": p["service_name"],
            "energy_kwh": p["energy_kwh"],
            "carbon_intensity_gco2e_per_kwh":
                p["carbon_intensity_gco2e_per_kwh"],
            "operational_emissions_gco2e": _round(op),
            "embodied_emissions_gco2e": _round(emb),
            "total_emissions_gco2e": _round(op + emb),
            "sci_gco2e_per_unit": _round((op + emb) / r)
        })

    total = operational + embodied

    return {
        "functional_unit": r,
        "functional_unit_name": unit_name,
        "services": lines,
        "total_energy_kwh": _round(energy),
        "operational_emissions_gco2e": _round(operational),
        "embodied_emissions_gco2e": _round(embodied),
        "total_emissions_gco2e": _round(total),
        "sci_gco2e_per_unit": _round(total / r)
    }