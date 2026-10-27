"""Published sources behind Health Hub's rules, shown under "Why?".

Every entry was looked up and checked by hand. Add a source here only after
opening it; rules refer to these by key.
"""

from __future__ import annotations

SOURCES: dict[str, dict[str, object]] = {
    "aasm_sleep_duration": {
        "title": "Recommended amount of sleep for a healthy adult: a joint consensus statement",
        "publisher": "American Academy of Sleep Medicine and Sleep Research Society (Watson et al.)",
        "year": 2015,
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC4434546/",
    },
    "sleep_regularity": {
        "title": "Sleep regularity is a stronger predictor of mortality risk than sleep duration",
        "publisher": "Sleep (Windred et al.)",
        "year": 2024,
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10782501/",
    },
    "who_activity": {
        "title": "World Health Organization 2020 guidelines on physical activity and sedentary behaviour",
        "publisher": "British Journal of Sports Medicine (Bull et al.)",
        "year": 2020,
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC7719906/",
    },
    "steps_mortality": {
        "title": "Daily steps and all-cause mortality: a meta-analysis of 15 international cohorts",
        "publisher": "The Lancet Public Health (Paluch et al.)",
        "year": 2022,
        "url": "https://doi.org/10.1016/S2468-2667(21)00302-9",
    },
    "resting_hr": {
        "title": "What's a normal resting heart rate?",
        "publisher": "Mayo Clinic",
        "year": None,
        "url": "https://www.mayoclinic.org/healthy-lifestyle/fitness/expert-answers/heart-rate/faq-20057979",
    },
    "spo2_t90": {
        "title": "Time under 90% oxygen saturation and systemic hypertension",
        "publisher": "Nature and Science of Sleep",
        "year": 2022,
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9719713/",
    },
    "max_hr": {
        "title": "Age-predicted maximal heart rate revisited",
        "publisher": "Journal of the American College of Cardiology (Tanaka et al.)",
        "year": 2001,
        "url": "https://doi.org/10.1016/S0735-1097(00)01054-8",
    },
}
