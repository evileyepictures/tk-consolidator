import os
import argparse
from logger import Logger
from asset import asset_from_path
from tank.errors import TankError

log = Logger()

class Delivery(object):
    """
    This class represent Shotgun Delivery entity. It provide access to most
    common attribute as well as cache data to this class member variables
    for faster access
    """

    def __init__(self, sg_instance, sg_id):

        self.sg = sg_instance

        self.sg_entity_type = 'Delivery'

        # Delivery fields that will be fetched from Shotgun
        self.sg_fields = [
            'sg_versions',
            'sg_delivery_type',
            'published_file_sg_delivery_published_files',
            'title',
            'sg_due_date'
        ]

        self.id = int(sg_id)
        self.sg_data = self._get_data()

    def _get_data(self):
        # Get specified delivery by ID with all the versions attached
        sg_delivery = self.sg.find_one(self.sg_entity_type, [
            ['id', 'is', self.id]], self.sg_fields
        )

        for f in self.sg_fields:
            if f in sg_delivery:
                continue
            raise Exception('Delivery dosn not have required field %s' % f)

        return sg_delivery

    def get_field(self, field_name):
        data = self.sg_data.get(field_name)

        if data == None:
            raise Exception(
                '%s is not specified on Shotgun for Delivery entity with id %s'
                % (field_name, self.sg_data['id'])
            )

        return data

    @property
    def type(self):
        field_name = 'sg_delivery_type'
        delivery_type = self.get_field(field_name)
        return delivery_type

    @property
    def title(self):
        title = self.sg_data.get('title')
        return title

    def get_versions(self):

        field_name = 'sg_versions'
        attached_delivery_versions = self.get_field(field_name)

        # If no versions attached to this delivery
        if not attached_delivery_versions:
            return []

        # Because we need to retrieve some extra fields for each delivery
        # we need to perform an extra query to Shotgun
        # Instead of making a call for each Version
        # we will form a single query to retrieve information about
        # all versions attached to this delivery at once. See more here:
        # https://github.com/shotgunsoftware/python-api/wiki/Reference%3A-Filter-Syntax
        version_filters = []
        for v in attached_delivery_versions:
            version_filters.append([ "id", "is", v['id']])
        filters = [
            {"filter_operator": "any", "filters": version_filters}
        ]

        delivery_versions = self.sg.find("Version", filters, ['sg_path_to_frames', 'code'])

        return delivery_versions

    def get_published_files(self):

        field_name = 'published_file_sg_delivery_published_files'
        attached_delivery_published_files = self.get_field(field_name)

        filters = []
        for p in attached_delivery_published_files:
            filters.append([ "id", "is", p['id']])
        filters = [
            {"filter_operator": "any", "filters": filters}
        ]

        delivery_publishes = self.sg.find("PublishedFile", filters, ['path', 'code'])

        return delivery_publishes

    def get_assets(self):

        delivery_assets = []

        # Get all of the Shotgun versions attached to this delivery
        delivery_versions = self.get_versions()
        # Get all of the Shotgun PublishedFiles attached to this delivery
        delivery_publihes = self.get_published_files()

        # Process version that attached to this delivery first
        for v in delivery_versions:
            path_to_frames = v.get('sg_path_to_frames')
            # Check if this version have path to frames
            if path_to_frames is not None:
                asset = asset_from_path(path_to_frames)
                delivery_assets.append(asset)
            else:
                log.warning('%s version has not frames attached' % v['code'])
                continue

        # Process Published Files that attached to this delivery
        for p in delivery_publihes:
            ppath = p.get('path', {})

            if ppath:
                local_path = ppath.get('local_path', '')
            else:
                log.warning('%s published file does not have any path attached' % p['code'])
                continue

            if local_path:
                asset = asset_from_path(local_path)
                delivery_assets.append(asset)
            else:
                log.warning('Local path is empty for %s' % v['code'])
                continue

        return delivery_assets


class Consolidator(object):

    def __init__(self, app, sg_delivery):

        self._app = app
        self.sg = self._app.shotgun
        self.tk = self._app.tank
        self.sg_delivery = sg_delivery

    def _find_sequence_range(self, path):
        """
        Helper method attempting to extract sequence information.

        Using the toolkit template system, the path will be probed to
        check if it is a sequence, and if so, frame information is
        attempted to be extracted.

        :param path: Path to file on disk.
        :returns: None if no range could be determined, otherwise (min, max)
        """
        # # find a template that matches the path:
        template = None
        try:
            template = self.parent.sgtk.template_from_path(path)
        except TankError:
            pass

        if not template:
            return None

        # get the fields and find all matching files:
        fields = template.get_fields(path)
        if "SEQ" not in fields:
            return None

        files = self.parent.sgtk.paths_from_template(template, fields, ["SEQ", "eye"])

        # find frame numbers from these files:
        frames = []
        for file in files:
            fields = template.get_fields(file)
            frame = fields.get("SEQ")
            if frame is not None:
                frames.append(frame)
        if not frames:
            return None

        # return the range
        return (min(frames), max(frames))

    def run(self):

        log.debug('Running the consolidator for Delivery id ', self.sg_delivery.id)

        # Get all delivery types listed in the project configuration
        delivery_types = self._app.get_setting("delivery_types", [])

        # Get configuration for the delivery type
        delivery_settings = {}
        for t in delivery_types:
            if t['name'] != self.sg_delivery.type:
                continue
            delivery_settings = t

        # Gather all of the assets attached to this delivery
        delivery_assets = self.sg_delivery.get_assets()
        delivery_due_date = self.sg_delivery.get_field('sg_due_date')
        due_year, due_month, due_day = [int(i) for i in delivery_due_date.split('-')]

        for asset in delivery_assets:
            # Check if any of the existing template can be applied to this path
            source_template = self.tk.template_from_path(str(asset.path))
            # Extract fields from current path
            fields = source_template.get_fields(str(asset.path))

            # Added extra fields that might be required by the template
            fields.update({
                'height': asset.height,
                'width': asset.width,
                'YYYY': due_year,
                'MM': due_month,
                'DD': due_day
            })

            step = fields.get('Step', '')
            if not step:
                log.error('Step was not determine from the source template.')
                continue

            # Get our final delivery template base on the asset type
            if asset.type == 'ImageSequence':

                if step == 'matte': # Use separate template for mattes
                    delivery_template_name = delivery_settings['matte_delivery_template']
                else:
                    delivery_template_name = delivery_settings['dpx_delivery_template']

            elif asset.type == 'VideoFile':
                delivery_template_name = delivery_settings['mov_delivery_template']
            else:
                log.error('Asset type %s is not supported!' % asset.type)

            delivery_template = self._app.get_template_by_name(delivery_template_name)

            if delivery_template is None:
                log.error(
                    'Failed to retrieve value for the template name: %s'
                    % delivery_template_name
                )

            # Build the new path base on the delivery template
            delivery_path = delivery_template.apply_fields(fields)

            # Do some integrity checks
            #
            # Check that file and its target template has the same type
            dest_ext = os.path.splitext(delivery_path)[1].lstrip('.')
            if asset.extension != dest_ext:
                log.error(
                    'Skipping %s. '
                    'Delivery asset type "%s" does not match '
                    'destination type "%s" defined by the template.'
                    %(asset.name, asset.extension, dest_ext))
                continue

            # Copy asset to delivery location
            asset.copy(delivery_path)

        log.success('Consolidation of "%s" delivery completed' % self.sg_delivery.title)


def parse_arguments(args):
    parser = argparse.ArgumentParser(description="App to export data for client delivery")

    parser.add_argument(
        '-id',
        required=True,
        help='run in ui mode',
    )

    args = parser.parse_args(args=args)

    return args


def run(app, *args):
    """
    Run application in command line mode
    """

    app_args = parse_arguments(args)

    # Create Delivery object that represent a single delivery item on SG
    sg_delivery = Delivery(app.shotgun, app_args.id)

    c = Consolidator(app, sg_delivery)
    c.run()
