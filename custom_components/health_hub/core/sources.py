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
    "resting_hr_mortality": {
        "title": "Resting heart rate and all-cause and cardiovascular mortality in the general population: a meta-analysis",
        "publisher": "CMAJ (Zhang et al.)",
        "year": 2016,
        "url": "https://pubmed.ncbi.nlm.nih.gov/26598376/",
    },
    "cadence_moderate": {
        "title": "Walking cadence (steps/min) and intensity in 21-40 year olds: CADENCE-adults",
        "publisher": "International Journal of Behavioral Nutrition and Physical Activity (Tudor-Locke et al.)",
        "year": 2019,
        "url": "https://doi.org/10.1186/s12966-019-0769-6",
    },
    "relative_intensity": {
        "title": "Cadence (steps/min) and relative intensity in 61 to 85-year-olds: the CADENCE-Adults study",
        "publisher": "International Journal of Behavioral Nutrition and Physical Activity (McAvoy et al.)",
        "year": 2023,
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC10688086/",
    },
    "rockport_walk": {
        "title": "Estimation of VO2max from a one-mile track walk, gender, age, and body weight",
        "publisher": "Medicine and Science in Sports and Exercise (Kline et al.)",
        "year": 1987,
        "url": "https://pubmed.ncbi.nlm.nih.gov/3600239/",
    },
    "fitness_reference": {
        "title": "Aerobic capacity reference data in 3816 healthy men and women 20-90 years",
        "publisher": "PLoS ONE (Loe et al.)",
        "year": 2013,
        "url": "https://doi.org/10.1371/journal.pone.0064319",
    },
    "fitness_mortality": {
        "title": "A simple nonexercise model of cardiorespiratory fitness predicts long-term mortality",
        "publisher": "Medicine and Science in Sports and Exercise (Nes et al.)",
        "year": 2014,
        "url": "https://pubmed.ncbi.nlm.nih.gov/24576863/",
    },
    "hr_ratio": {
        "title": "Estimation of VO2max from the ratio between HRmax and HRrest: the Heart Rate Ratio Method",
        "publisher": "European Journal of Applied Physiology (Uth et al.)",
        "year": 2004,
        "url": "https://doi.org/10.1007/s00421-003-0988-y",
    },
    "hr_ratio_general": {
        "title": "Estimating maximal oxygen uptake from the ratio of heart rate at maximal exercise to heart rate at rest in middle-aged men",
        "publisher": "The World Journal of Men's Health (Voutilainen et al.)",
        "year": 2021,
        "url": "https://doi.org/10.5534/wjmh.200055",
    },
}
