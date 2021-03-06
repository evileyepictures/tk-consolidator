import os
import sys
import re
import argparse
import logging
import sgtk

import asset
from asset import asset_from_path
from tank.errors import TankError

debug = os.environ.get('DRY_RUN', False)

# Get logger for the current app namespace
log = logging.getLogger('tank.setup_project.consolidator')
if debug:
    log.setLevel(logging.DEBUG)
# Pass this logger to the parent asset module
# that it can log with the same handlers and formatting
asset.set_logger(log)


class Delivery(object):
    """
    This class represent Shotgun Delivery entity. It provide access to most
    common attribute as well as cache shotgun site data to this class member variables
    for faster access
    """

    def __init__(self, sg_instance, sg_id):

        # NOTE(Kirill): self._app dependency is not desirable here
        self._app = sgtk.platform.current_bundle()
        self.sg = sg_instance
        self.sg_entity_type = 'Delivery'
        status = self._app.get_setting('delivery_status', [])
        # status = 'eepfin'

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

        self.all_delivery_versions = self._get_versions_by_status(status)

        self.__versions = []
        self.__published_files = []

    def _get_data(self):
        """ Get specified delivery by ID with all the versions attached """

        filters = [
            ['project', 'is', self._app.context.project],
            ['id', 'is', self.id]
        ]
        sg_delivery = self.sg.find_one(self.sg_entity_type, filters, self.sg_fields)

        for f in self.sg_fields:
            if f in sg_delivery:
                continue
            raise Exception('Delivery dosn not have required field %s' % f)

        return sg_delivery

    def _get_versions_by_status(self, status):
        """
        Get all versions that have final_status value in the status field

        :return: Dictionary of shotgun Version grouped by its entity id like
            {
                2414: {
                    'sg_status_list': eepfin,
                    'eepfin', 'code': 'Sub0150 comp comp v029 pjpeg',
                    'type': 'Version',
                    'id': 7550
                },
                2341: ...
            }
        """
        filters = [
            ['project', 'is', self._app.context.project],
            ['sg_status_list', 'is', status]
        ]
        fields = ['code', 'sg_status_list', 'entity']
        versions = self.sg.find('Version', filters, fields)

        # Group finaled versions by its entity ID
        v_by_entity_id = {}
        for v in versions:
            entity_id = v['entity']['id']
            del v['entity']
            v_by_entity_id[entity_id] = v

        return v_by_entity_id

    def _normalize_path(self, path):
        """
        This function make sure that the path is converted to the current OS format

        Because Shotgun Versions entity can only store OS specific paths to files
        we need to make sure that those paths were converted.
        For example if the current OS is Mac but the Version was created
        on Windows the file path will be Windows specific which will case an error
        """
        conf = self._app.tank.pipeline_configuration
        project_name = conf.get_project_disk_name()

        path = path.replace('\\', '/')

        # XXX: _roots is the private method, I should not really use it
        # However the alternative would be to read the roots yaml manually
        for os_name, root in conf._roots['primary'].items():
            proj_root = os.path.join(root, project_name)
            proj_root = proj_root.replace('\\', '/')
            path = path.replace(proj_root, self._app.tank.project_path)

        path = os.path.normpath(path)

        return path

    def get_field(self, field_name):
        """
        Utility method to get a value of SG field of this delivery
        Note: this only works with pre cached values by this class.
        If you need to extend this list add your value to self.sg_fields
        it will make it available via this method without making a call to SG
        """
        data = self.sg_data.get(field_name)

        if data is None:
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
        """
        Get full information for every Version attached to this delivery
        """

        if self.__versions:
            return self.__versions

        field_name = 'sg_versions'
        attached_dl_vers = self.get_field(field_name)

        # If no versions attached to this delivery
        if not attached_dl_vers:
            return []

        # Because we need to retrieve some extra fields for each delivery
        # we need to perform an extra query to Shotgun
        # Instead of making a call for each Version
        # we will form a single query to retrieve information about
        # all versions attached to this delivery at once. See more here:
        # https://github.com/shotgunsoftware/python-api/wiki/Reference%3A-Filter-Syntax
        version_filters = []
        for v in attached_dl_vers:
            version_filters.append(['id', 'is', v['id']])

        filters = [
            {'filter_operator': 'any', 'filters': version_filters}
        ]
        fields = ['sg_path_to_frames', 'sg_path_to_movie', 'code', 'entity']
        delivery_versions = self.sg.find('Version', filters, fields)

        self.__versions = delivery_versions

        return delivery_versions

    def get_published_files(self):

        if self.__published_files:
            return self.__published_files

        field_name = 'published_file_sg_delivery_published_files'
        attached_dl_published_files = self.get_field(field_name)

        if not attached_dl_published_files:
            return []

        filters = []
        for p in attached_dl_published_files:
            filters.append(["id", "is", p['id']])

        filters = [
            {'filter_operator': 'any', 'filters': filters}
        ]
        fields = ['path', 'code', 'entity']
        delivery_publishes = self.sg.find('PublishedFile', filters, fields)

        self.__published_files = delivery_publishes

        return delivery_publishes

    def get_assets(self):
        """
        Get complete list of asset that need to be processed for this delivery
        """

        dl_assets = []  # Final delivery assets
        delivery_paths = []  # To track duplicated paths

        # Get all of the Shotgun versions attached to this delivery
        delivery_versions = self.get_versions()
        # Get publishes that attached to this delivery
        delivery_publihes = self.get_published_files()

        # Process versions frames first
        for v in delivery_versions:

            # This path are relative to the platform
            # from which they were published
            # We need to make it relative to the current platform project path
            path_to_frames = v.get('sg_path_to_frames')

            # Check if this version have path to frames
            if path_to_frames is None:
                log.warning('%s version has no frames attached' % v['code'])
                continue

            path_to_asset = self._normalize_path(path_to_frames)

            if path_to_asset in delivery_paths:
                continue

            try:
                asset = asset_from_path(path_to_asset)
            except Exception as e:
                log.error('Can not create asset from path %s. %s' % (path_to_asset, e))
                raise

            fin_version = self.all_delivery_versions.get(v['entity']['id'])
            asset.extra_attrs['final_version'] = fin_version

            asset.sg_data = v
            dl_assets.append(asset)
            delivery_paths.append(path_to_asset)

        # Process versions mov
        for v in delivery_versions:
            path_to_movies = v.get('sg_path_to_movie')
            # Append Version attached mov file to asset list
            if path_to_movies is None:
                log.warning('%s version has no mov attached' % v['code'])
                continue

            path_to_asset = self._normalize_path(path_to_movies)

            if path_to_asset in delivery_paths:
                continue

            asset = asset_from_path(path_to_asset)

            fin_version = self.all_delivery_versions.get(v['entity']['id'])
            asset.extra_attrs['final_version'] = fin_version

            asset.sg_data = v
            dl_assets.append(asset)
            delivery_paths.append(path_to_asset)

        # Process PublishedFiles
        for p in delivery_publihes:

            ppath = p.get('path', {})

            if ppath:
                local_path = ppath.get('local_path', '')
            else:
                log.warning(
                    '%s published file does not have any path attached'
                    % p['code']
                )
                continue

            if not local_path:
                log.warning('Local path is empty for %s' % v['code'])
                continue

            if local_path in delivery_paths:
                continue

            asset = asset_from_path(local_path)

            fin_version = self.all_delivery_versions.get(v['entity']['id'])
            asset.extra_attrs['final_version'] = fin_version

            asset.sg_data = p
            dl_assets.append(asset)
            delivery_paths.append(local_path)

        return dl_assets


class Consolidator(object):
    """
    This is main application class. It responsible for hight level logic such as

        - Copy assets that attached to selected Shotgun delivery
        - Renaming assets according to predefine name template
        - Providing other interfaces for filtering assets and QA

    Note: It should not include any logic that deal
    with shotgun api or make any calls to SG site

    Usage:

        To run consolidator on Shotgun delivery entity with id 12:
            >>> tank consolidator -id 12

        You can filter out copied file base on the file extension:
            >>> tank consolidator -id 12 -ef mov

        You can also filter out base on Shotgun entity type:
            >>> tank consolidator -id 12 -stf PublishedFile
    """

    def __init__(self, app, sg_delivery, options):
        """
        :param app: Shotgun Toolkit application instance
        :param sg_delivery: Delivery object that consolidator run for
        :param options: Options dictionary that come from command line or UI
        """

        self._app = app
        self.sg = self._app.shotgun
        self.tk = self._app.tank
        self.sg_delivery = sg_delivery
        self.opt = options

        if self.opt.sg_type_filter is not None:
            self.sg_type_filter = self.opt.sg_type_filter
        else:
            self.sg_type_filter = []

        if self.opt.extension_filter is not None:
            # All file extension filters should be lowercase
            self.ext_filter = [i.lower() for i in self.opt.extension_filter]
        else:
            self.ext_filter = []

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

    def version_from_name(self, name):
        """
        Try to determine file version from its name base on different regex patterns

        :returns: None or integer
        """
        version_patterns = [
            '([vV])(?P<version_number>[0-9]+)',  # v001, V00001
            '([A-Za-z]+)_(?P<version_number>[0-9]+)'  # name_01
        ]

        # Return firs matched pattern in self.version_patterns list
        for p in version_patterns:
            result = re.finditer(p, name)
            if result is not None:
                # log.debug('Regex version result: %s', result.group('version_number'))
                version = None
                # We alway want to use version found at the and of the name
                # e.g. for name like 'rvb300_match_30mlCamZv03_v006.fbx' we should return 6 not 3
                for v in result:
                    version = int(v.group('version_number'))

                return version

        return None

    def get_final_version(self, asset):
        """
        According to EEP business logic the final delivery version should
        always match the version that has "delivery_status" on Shotgun.
        "delivery_status" is defined in project configuration yaml file.
        If this function failed to acquire the final version it will fall back
        to the asset version.
        """
        try:
            fin_ver_code = asset.extra_attrs['final_version']['code']
        except Exception as e:
            log.debug(
                'Failed to retrieve eep final version from asset %s. %s'
                % (asset.name, e)
            )
            return int(asset.version)

        version_number = self.version_from_name(fin_ver_code)

        if version_number is None:
            return int(asset.version)
        else:
            return version_number

        # result = re.search(r'(v)([0-9]+)', fin_ver_code)
        # if result:
        #     return int(result.groups()[1])
        # else:
        #     return int(asset.version)

    def run(self):
        """
        Then app run in cmd mode this function gets run
        """

        log.info('Consolidating %s' % self.sg_delivery.title)

        # Get all delivery types listed in the project configuration
        dl_types = self._app.get_setting('delivery_types', [])

        # Get configuration for the delivery type
        dl_settings = {}
        for t in dl_types:
            if t['name'] != self.sg_delivery.type:
                continue
            dl_settings = t

        # Gather all of the assets attached to this delivery
        dl_assets = self.sg_delivery.get_assets()
        delivery_due_date = self.sg_delivery.get_field('sg_due_date')
        due_year, due_month, due_day = [int(i) for i in delivery_due_date.split('-')]

        # Asset filtering logic
        filtered_assets = []
        for asset in dl_assets:
            # Exclude asset by its shotgun file type specified in the filter
            if asset.sg_data['type'] in self.sg_type_filter:
                continue
            # Exclude asset that match the ext_filter extensions
            if asset.extension.lower() in self.ext_filter:
                continue
            filtered_assets.append(asset)
        dl_assets = filtered_assets

        asset_completed = []  # Hold asset that have been successfuly consolidated

        for asset in dl_assets:

            log.info('-'*79)
            log.info('Consolidating %s' % asset.name)

            # Check if any of the existing template can be applied to this path
            source_template = self.tk.template_from_path(str(asset.path))

            if source_template is None:
                log.warning(
                    'File %s does not match any existing path templates'
                    % asset.path
                )
                continue

            # Extract fields from current path
            fields = source_template.get_fields(str(asset.path))

            final_version = self.get_final_version(asset)

            # Added extra fields that might be required by the template
            fields.update({
                'delivery_title': self.sg_delivery.title,
                'version': final_version,
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
                
                if 'output' in fields:
                    dl_template_name = dl_settings['matte_delivery_template']
                else:
                    dl_template_name = dl_settings['dpx_delivery_template']

                seq_width = dl_settings.get('sequence_width', False)
                seq_height = dl_settings.get('sequence_height', False)

                # Check resolution
                if seq_width and seq_height:
                    if seq_width != fields['width'] or seq_height != fields['height']:
                        if self.opt.force:
                            log.warning('Sequence resolution doesn not match %sx%s' % (seq_width, seq_height))
                        else:
                            log.error('Skipping. Sequence resolution doesn not match %sx%s' % (seq_width, seq_height))
                            continue

            elif asset.type == 'VideoFile':
                dl_template_name = dl_settings['mov_delivery_template']
            elif asset.type == 'ImageFile':
                dl_template_name = dl_settings['img_delivery_template']
                fields.update({'img_ext': asset.extension})
            else:
                log.error('Asset type %s is not supported!' % asset.type)
                continue

            dl_template = self._app.get_template_by_name(dl_template_name)

            if dl_template is None:
                log.error(
                    'Failed to retrieve value for the template name: %s'
                    % dl_template_name
                )

            # Before passing this fields to the path constructor
            # run a user defined hook to do custom manipulations with the fields
            # This allows for custom per delivery type name customization
            fields = self._app.execute_hook_method(
                'hook_customize_fields', 'execute',
                fields=fields, delivery=self.sg_delivery
            )

            # HACK(Kirill): This is a hacky way to handle assets
            # In order to handle it "Shotgun" way we need to create
            # separate path templates for asset and shots
            asset_name = fields.get('Asset', False)
            if asset_name:
                fields.update({'Shot': asset_name})

            # Build the new path base on the delivery template
            delivery_path = dl_template.apply_fields(fields)

            # Do some integrity checks
            #
            # Check that file and its target template has the same type
            dest_ext = os.path.splitext(delivery_path)[1].lstrip('.')
            if asset.extension != dest_ext:
                log.error(
                    'Skipping %s. '
                    'Delivery asset type "%s" does not match '
                    'destination type "%s" defined by the template.'
                    % (asset.name, asset.extension, dest_ext))
                continue

            if debug:
                asset.copy(delivery_path, dry_run=True)
            else:
                # Copy asset to delivery location
                asset.copy(delivery_path)

            asset_completed.append(asset)

        # Output final summary log for the user
        # 
        asset_not_completed = list(set(dl_assets) - set(asset_completed))
        
        print ''

        if len(asset_completed) < len(dl_assets):
            print 'WARNING! The following assets were not consolidated:'
            for i, asset in enumerate(asset_not_completed):
                print ''
                print '    %s. %s' % (i+1, asset.name)
            print ''          
            print (
              'Please review your consolidation log. '
              'You might be able to force consolidation of this assets by running consolidator with -f flag.'
            )
        else:
            print (
                'All assets have been consolidated for "%s" delivery. Yay! :)'
                % self.sg_delivery.title
            )


def parse_arguments(args):

    parser = argparse.ArgumentParser(
        description="command line application that prepare production assets for delivery"
    )
    parser.add_argument(
        '-id',
        required=True,
        help='shotgun delivery id',
    )
    parser.add_argument(
        '-stf', nargs='+', metavar='TYPE', dest='sg_type_filter',
        help='exclude assets from processing by its shotgun entity type',
    )
    parser.add_argument(
        '-ef', nargs='+',  metavar='EXT', dest='extension_filter',
        help='exclude assets from processing by its extension',
    )

    parser.add_argument('--force', '-f', help='force consolidation for assets with warnings', action='store_true')

    # No arguments provided
    # Print help and exit
    if len(sys.argv) == 2:
        print  # Empty line
        parser.print_help()
        print  # Empty line
        exit(0)

    args = parser.parse_args(args=args)

    return args


def run(app, *args):
    """
    Run application in command line mode
    """

    app_args = parse_arguments(args)

    # Create Delivery object that represent a single delivery item on SG
    sg_delivery = Delivery(app.shotgun, app_args.id)

    c = Consolidator(app, sg_delivery, app_args)
    c.run()
