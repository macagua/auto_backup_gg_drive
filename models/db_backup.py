import os
import json
import requests
import shutil


from datetime import datetime, timedelta

from odoo import api, fields, models, _
from odoo.addons.google_drive.models.google_drive import GoogleDrive
from odoo.exceptions import UserError
from odoo.service import db


import logging

_logger = logging.getLogger(__name__)


class DbBackup(models.Model):
    _inherit = 'db.backup'

    method = fields.Selection(
        selection_add=[("gg_drive", "Google drive")]
    )
    drive_folder_id = fields.Char(
        string='Drive Folder ID',
        help="Create a folder on drive in which you want to upload files; get the drive_folder_id from URL"
    )
    @api.depends("folder", "method", "sftp_host", "sftp_port", "sftp_user")
    def _compute_name(self):
        super(DbBackup, self)._compute_name()
        """Get the right summary for this job."""
        for rec in self:
            if rec.method == "gg_drive":
                gg_drive_env = self.env['google.drive.config']
                access_token = GoogleDrive.get_access_token(gg_drive_env)
                if not access_token:
                    UserError(_('Please input Google drive access_token'))
                else:
                    rec.name = "Google Drive - Token: %s-****" % (access_token[:5])

    def action_backup(self):
        super(DbBackup, self).action_backup()
        self.action_backup_gg_drive()

    def action_backup_gg_drive(self):
        gg_drive_env = self.env['google.drive.config']
        access_token = GoogleDrive.get_access_token(gg_drive_env)
        self._action_backup_gg_drive(access_token)
        self._action_remove_backup_gg_drive(access_token)

    def _action_backup_gg_drive(self, access_token):
        backup = None
        successful = self.browse()
        # Backup and upload to GG Drive
        gg_drive = self.filtered(lambda r: r.method == "gg_drive")
        for rec in gg_drive:
            dbname = self.env.cr.dbname
            filename = '%s_%s' % (dbname, self.filename(datetime.now(), ext=rec.backup_format))
            file_path = os.path.join(rec.folder, filename)
            with rec.backup_log():
                # Directory must exist
                try:
                    os.makedirs(rec.folder, exist_ok=True)
                except OSError as exc:
                    _logger.exception("Action backup - OSError: %s" % exc)

                with open(file_path, "wb") as destiny:
                    # Copy the cached backup
                    if backup:
                        with open(backup) as cached:
                            shutil.copyfileobj(cached, destiny)
                    # Generate new backup
                    else:
                        db.dump_db(
                            self.env.cr.dbname, destiny, backup_format=rec.backup_format
                        )
                        backup = backup or destiny.name
                    if backup:
                        # GOOGLE DRIVE UPLOAD
                        headers = {"Authorization": "Bearer %s" % (access_token)}
                        params = {
                            "name": "%s" % (str(filename)),
                            "parents": ["%s" % (str(rec.drive_folder_id))]
                        }
                        files = {
                            'data': ('metadata', json.dumps(params), 'application/json; charset=UTF-8'),
                            'file': open("%s" % (str(file_path)), "rb")
                        }
                        try:
                            response = requests.post(
                                "https://www.googleapis.com/upload/drive/v3/files?uploadType=multipart",
                                headers=headers,
                                files=files
                            )
                            _logger.info(_('Database upload to Google drive success %s' % response))
                        except Exception as error:
                            _logger.exception(_('Database upload to Google drive error %s' % error))
                        successful |= rec
        successful.cleanup()

    def _action_remove_backup_gg_drive(self, access_token):
        gg_drive = self.filtered(lambda r: r.method == "gg_drive")
        for rec in gg_drive:
            if rec.days_to_keep > 0:
                headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
                params = {
                    'access_token': access_token,
                    'q': "mimeType='application/%s'" % (rec.backup_format),
                    'fields': "nextPageToken,files(id,name, createdTime, modifiedTime, mimeType)"
                }
                uri = "/drive/v3/files"
                try:
                    status, data, time = self.env['google.service']._do_request(
                        uri, params=params, headers=headers, method='GET')
                    _logger.info('_do_request for %s' % uri)
                except requests.HTTPError as error:
                    _logger.exception(_('google_service error %s' % error))

                for item in data['files']:
                    date_today = datetime.today().date()
                    create_date = datetime.strptime(str(item['createdTime'])[0:10], '%Y-%m-%d').date()

                    delta = date_today - create_date
                    if delta.days >= rec.days_to_keep:
                        params = {
                            'access_token': access_token
                        }
                        uri = "/drive/v3/files/%s" % (item['id'])
                        try:
                            status, data, time = self.env['google.service']._do_request(
                                uri, params=params, headers=headers, method='DELETE')
                            _logger.info(_('Delete file from Google drive success %s' % data))
                        except requests.HTTPError as error:
                            _logger.exception(_('delete google_service error %s' % error))
