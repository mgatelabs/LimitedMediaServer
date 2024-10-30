class AppPropertyDefinition:
    """
    Class to define application properties with validation.

    :param property_id: The property identifier.
    :param default_value: The default value of the property.
    :param comment: A comment describing the property.
    :param validators: A list of validator functions for the property.
    """

    def __init__(self, property_id: str, default_value, comment: str, validators=None):
        if validators is None:
            validators = []
        self.id = property_id
        self.default_value = default_value
        self.comment = comment
        self.validators = validators

    def get_default_value(self) -> str:
        """
        Get the default value of the property.

        :return: The default value.
        """
        if callable(self.default_value):
            return self.default_value()
        return self.default_value

    def is_valid(self, value: str) -> str | None:
        """
        Validate the property value using the defined validators.

        :param value: The value to validate.
        :return: None if valid, otherwise an error message.
        """
        for validator in self.validators:
            error = validator(value)
            if error:
                return error
        return None