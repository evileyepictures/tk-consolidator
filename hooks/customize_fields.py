import sgtk
from sgtk import Hook
from sgtk import TankError

class CustomizeFields(Hook):
    """
    //
    """

    def execute(self, fields, delivery, **kwargs):
        """
        :params fields: Template field which used to construct the final
        delivery path. Modifying this field will alter the final file name
        :params delivery: Delivery object

        :returns: Dictionary of modified delivery fields
        """

        if delivery.type == 'to_technicolor':
            fields.update({'Shot': fields['Shot'].upper()})
        else:
            pass
        return fields
