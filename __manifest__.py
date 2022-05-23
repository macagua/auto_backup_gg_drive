# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).
{
    "name": "Database Auto-Backup Google Drive",
    "summary": "Backups database",
    "version": "13.0.1.0.0",
    "author": "vuna2004@gmail.com",
    "license": "AGPL-3",
    "website": "https://github.com/OCA/server-tools",
    "category": "Tools",
    "depends": ["auto_backup", "google_drive"],
    "data": [
        # views
        "views/db_backup.xml",
    ],
    "installable": True,
}
