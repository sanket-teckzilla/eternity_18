{
    "name": " Daily Analysis Email Reporting",
    "version": "1.0",
    "summary": "Daily analysis Email Report",
    "sequence": "1",
    "category": "email",
    "author": "TECHNOGEO SOFT Pvt. Ltd.",
    "website": "http://www.geotechnosoft.com",
    "description": """
    
        """,
    "license": "LGPL-3",
    "installable": True,
    "depends": ['base', 'account', 'sale', 'crm', 'mrp', 'purchase',],
    "data": [
        'security/security_view.xml',
        'views/daily_analysis.xml',
    ],
}
