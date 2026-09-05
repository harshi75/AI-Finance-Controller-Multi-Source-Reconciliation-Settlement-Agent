"""
Small tax rule corpus for the Tax-Line Matcher.

In production this would be a proper document store (GST circulars, HSN/SAC
code tables, etc.) — for the hackathon this is enough to demonstrate the
retrieval + classification pattern without needing a real tax database.
"""

TAX_RULES = [
    {
        "tax_code": "GST_SAC_9971",
        "category": "Payment Gateway / Financial Services",
        "description": "Financial and related services including payment processing, "
                        "gateway settlement, and transaction fees charged by payment "
                        "aggregators. Applicable GST rate 18%.",
    },
    {
        "tax_code": "GST_SAC_9983",
        "category": "Software as a Service",
        "description": "Cloud computing, hosting, and software subscription services "
                        "including AWS, cloud infrastructure, and SaaS platform fees. "
                        "Applicable GST rate 18%.",
    },
    {
        "tax_code": "GST_SAC_9963",
        "category": "Food Delivery / Restaurant Services",
        "description": "Food delivery platform commissions and restaurant aggregator "
                        "services such as Zomato and Swiggy payouts. Applicable GST rate "
                        "5% without input tax credit, or 18% for platform commission.",
    },
    {
        "tax_code": "GST_SAC_9964",
        "category": "Passenger Transport Services",
        "description": "Ride-hailing and passenger transport aggregator commissions, "
                        "such as Uber trip settlements. Applicable GST rate 5%.",
    },
    {
        "tax_code": "TDS_194C",
        "category": "TDS on Contractual Payments",
        "description": "Tax deducted at source on payments to contractors and "
                        "sub-contractors for work performed. Applicable rate 1-2% "
                        "depending on payee type.",
    },
    {
        "tax_code": "TDS_194J",
        "category": "TDS on Professional/Technical Fees",
        "description": "Tax deducted at source on fees for professional or technical "
                        "services, including consulting and software development. "
                        "Applicable rate 10%.",
    },
    {
        "tax_code": "GST_EXEMPT",
        "category": "Exempt Supply",
        "description": "Transactions exempt from GST including certain financial "
                        "instruments, interest payments, and specified exempt goods "
                        "or services.",
    },
    {
        "tax_code": "REVERSE_CHARGE",
        "category": "Reverse Charge Mechanism",
        "description": "Transactions where the recipient, not the supplier, is liable "
                        "to pay GST — typically for imported services or specified "
                        "categories of unregistered suppliers.",
    },
    {
        "tax_code": "GST_SAC_9954",
        "category": "Construction and Real Estate Services",
        "description": "Construction, works contract, and real estate development "
                        "services including building, renovation, and property "
                        "management fees. Applicable GST rate 18%, or 5% for certain "
                        "residential construction.",
    },
    {
        "tax_code": "GST_SAC_9972",
        "category": "Real Estate Rental / Leasing",
        "description": "Renting or leasing of immovable property for commercial use, "
                        "office space rentals, and warehouse leasing fees. Applicable "
                        "GST rate 18%.",
    },
    {
        "tax_code": "GST_SAC_9997",
        "category": "Insurance Services",
        "description": "Life insurance, general insurance, and reinsurance premium "
                        "payments and commissions. Applicable GST rate 18% on "
                        "commission, special rates on premium components.",
    },
    {
        "tax_code": "GST_SAC_9983_ADV",
        "category": "Advertising and Marketing Services",
        "description": "Digital advertising, ad-tech platform fees, marketing agency "
                        "commissions, and sponsored content payments such as Google Ads "
                        "or Meta Ads spend. Applicable GST rate 18%.",
    },
    {
        "tax_code": "GST_SAC_9982",
        "category": "Legal and Compliance Services",
        "description": "Legal counsel fees, compliance advisory, notary services, and "
                        "regulatory filing charges. Applicable GST rate 18%, often under "
                        "reverse charge for individual advocates.",
    },
    {
        "tax_code": "TDS_194H",
        "category": "TDS on Commission or Brokerage",
        "description": "Tax deducted at source on commission or brokerage payments to "
                        "agents, dealers, and intermediaries. Applicable rate 5%.",
    },
    {
        "tax_code": "TDS_194I",
        "category": "TDS on Rent",
        "description": "Tax deducted at source on rent payments for land, building, "
                        "furniture, or machinery. Applicable rate 2% for machinery, "
                        "10% for land/building.",
    },
    {
        "tax_code": "TDS_192",
        "category": "TDS on Salary",
        "description": "Tax deducted at source on employee salary and wage payments, "
                        "computed per applicable income tax slab rates.",
    },
    {
        "tax_code": "NON_GST_INTEREST",
        "category": "Interest Income",
        "description": "Interest earned on fixed deposits, loans, or bonds. Outside "
                        "GST scope; subject to income tax and TDS under section 194A "
                        "where applicable.",
    },
    {
        "tax_code": "NON_GST_DIVIDEND",
        "category": "Dividend Income",
        "description": "Dividend payments received from equity holdings or mutual "
                        "funds. Outside GST scope; subject to income tax and TDS under "
                        "section 194 where applicable.",
    },
    {
        "tax_code": "IGST_IMPORT",
        "category": "Import of Goods or Services (IGST)",
        "description": "Integrated GST applicable on import of goods or services from "
                        "outside India, including cross-border software licenses and "
                        "international vendor payments. Rate varies by HSN/SAC code.",
    },
    {
        "tax_code": "TCS_ECOMMERCE",
        "category": "E-commerce Operator TCS",
        "description": "Tax collected at source by e-commerce operators on payments "
                        "made to sellers on their platform, applicable at 1% under "
                        "section 52 of the CGST Act.",
    },
]
