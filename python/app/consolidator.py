import argparse

from logger import Logger
from asset import asset_from_path

log = Logger()

class Delivery(object):

    def __init__(self, app, sg_id):
        self._app = app
        self.sg = self._app.shotgun

        self.sg_entity_type = 'Delivery'
        self.sg_fields = ['sg_versions', 'sg_delivery_type']

        self.id = int(sg_id)
        self.sg_data = self._get_data()

    def _get_data(self):
        # Get specified delivery by ID with all the versions attached
        sg_delivery = self.sg.find_one(self.sg_entity_type, [
            ['id', 'is', self.id]], self.sg_fields
        )
        return sg_delivery

    @property
    def type(self):
        delivery_type = self.sg_data.get('sg_delivery_type')
        return delivery_type

    def get_versions(self):

        delivery_versions = self.sg_data.get('sg_versions')

        if delivery_versions == None:
            log.warning('Delivery has no sg_versions field')
            return []
        if len(delivery_versions) == 0:
            log.warning('No versions attached to this delivery')
            return []

        # Because we need to retrive some extra fields for each delivery
        # we need to perform an extra quiry to Shotgun
        # Instead of making a call for each Version
        # we will form a single quiry to retrive information about
        # all versions attached to this delivery at once. See more here:
        # https://github.com/shotgunsoftware/python-api/wiki/Reference%3A-Filter-Syntax
        version_filters = []
        for v in self.sg_data['sg_versions']:
            version_filters.append([ "id", "is", v['id']])
        filters = [
            {"filter_operator": "any", "filters": version_filters}
        ]

        delivery_versions = self.sg.find("Version", filters, ['sg_path_to_frames'])

        return delivery_versions

class Consolidator(object):

    def __init__(self, app, args):

        self._args = self._parse_arguments(args)

        self._app = app
        self.sg = self._app.shotgun
        self.tk = self._app.tank

    def _parse_arguments(self, args):
        parser = argparse.ArgumentParser(description="App to export data for client delivery")

        parser.add_argument(
            '-id',
            required=True,
            help='run in ui mode',
        )

        args = parser.parse_args(args=args)

        return args

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
        log.debug('Running the consolidator for Delivery id ', self._args.id)

        # template = self._app.get_template('')
        delivery_types = self._app.get_setting("delivery_types", [])

        sg_delivery = Delivery(self._app, self._args.id)

        delivery_versions = sg_delivery.get_versions()

        # Get configuration for the dilivery type
        delivery_settings = {}
        for t in delivery_types:
            if t['name'] != sg_delivery.type:
                continue
            delivery_settings = t

        # Get our final delivery template
        delivery_template_name = delivery_settings['sequence_delivery_template']
        delivery_template = self._app.get_template_by_name(delivery_template_name)

        if delivery_template is None:
            log.error('Failed to retrive value fot the template name: %s' % template_name)

        # Now we have all of the version it is time to proccess it
        for v in delivery_versions:
            path_to_frames = v.get('sg_path_to_frames')
            log.debug('Path to frames: %s' % path_to_frames)

            asset = asset_from_path(path_to_frames)

            # Check if any of the existing template can be applied to this path
            source_template = self.tk.template_from_path(path_to_frames)
            # Extract fields from current path
            fields = source_template.get_fields(path_to_frames)
            # Buid the new path
            delivery_path = delivery_template.apply_fields(fields)

            import pdb; pdb.set_trace()

            # We need to form each path to corresponding delivery template
            # for the specific vendor
            #

def run(app, *args):
    c = Consolidator(app, args)
    c.run()
