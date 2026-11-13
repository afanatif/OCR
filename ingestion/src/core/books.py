"""
Centralized metadata for all MCQ books.
Each entry defines the file path, year, subject, and hardcoded TOC.
"""

BOOK_METADATA: dict[str, dict] = {
    "physiology_mcqs": {
        "display_name": "physiology_mcqs",
        "year": "year_1",
        "subject": "Physiology",
        "filename": "Physiology MCQs Book.pdf",
        "toc": {
            1:  "The cell and general physiology",
            2:  "Membrane physiology, nerve, and muscle",
            3:  "The heart",
            4:  "The circulation",
            5:  "The body fluids and kidneys",
            6:  "Blood cells, immunity, and blood coagulation",
            7:  "Respiration",
            8:  "Aviation, space, and deep-sea diving physiology",
            9:  "The nervous system: a. general principles and sensory physiology",
            10: "The nervous system: b. the special senses",
            11: "The nervous system: c. motor and integrative neurophysiology",
            12: "Gastrointestinal physiology",
            13: "Metabolism and temperature regulation",
            14: "Endocrinology and reproduction",
            15: "Sports physiology",
        },
    },
    # Example for adding new books:
    # "anatomy_mcqs": {
    #     "display_name": "anatomy_mcqs",
    #     "year": "year_1",
    #     "subject": "Anatomy",
    #     "filename": "Anatomy MCQs Book.pdf",
    #     "toc": { 1: "Introduction", 2: "Upper Limb" ... }
    # },
}
