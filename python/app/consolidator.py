import argparse

from logger import Logger
from asset import asset_from_path

log = Logger()

class Delivery(object):

    def __init__(self, sg_instance, sg_id):

        self.sg = sg_instance

        self.sg_entity_type = 'Delivery'
        self.sg_fields = ['sg_versions', 'sg_delivery_type', 'title']

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

        if len(data) == 0:
            raise Exception(
                'The required field %s is not populated on Shotgun!'
                % field_name
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

        # Because we need to retrive some extra fields for each delivery
        # we need to perform an extra quiry to Shotgun
        # Instead of making a call for each Version
        # we will form a single quiry to retrive information about
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

        # Get all of the Shotgun versions attached to this delivery
        delivery_versions = self.sg_delivery.get_versions()

        # Get configuration for the dilivery type
        delivery_settings = {}
        for t in delivery_types:
            if t['name'] != self.sg_delivery.type:
                continue
            delivery_settings = t

        # Get our final delivery template
        delivery_template_name = delivery_settings['sequence_delivery_template']
        delivery_template = self._app.get_template_by_name(delivery_template_name)

        if delivery_template is None:
            log.error('Failed to retrive value fot the template name: %s' % template_name)

        # Now we have all of the version it is time to proccess it
        for v in delivery_versions:

            log.line()
            log.info('Processing version %s with id %s' % (v['code'], v['id']))

            path_to_frames = v.get('sg_path_to_frames')

            # Check if this version have path to frames
            if path_to_frames is not None:

                asset = asset_from_path(path_to_frames)

                # Check if any of the existing template can be applied to this path
                source_template = self.tk.template_from_path(path_to_frames)
                # Extract fields from current path
                fields = source_template.get_fields(path_to_frames)
                # Buid the new path base on the delivery template
                delivery_path = delivery_template.apply_fields(fields)

                # Copy asset to delivery location
                asset.copy(delivery_path)

            else:
                log.warning(
                    'Version %s does not have any sequences attached to it. Skipping!'
                    % v['code']
                )

            # Do something else with the version or it attributes
            #

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

    app_args = parse_arguments(args)

    # Create Delivery object that represent a single dilivery item on SG
    sg_delivery = Delivery(app.shotgun, app_args.id)

    c = Consolidator(app, sg_delivery)
    c.run()
