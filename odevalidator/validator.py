import configparser
import dateutil.parser
import json
import logging
from decimal import Decimal
from pathlib import Path
import queue
from .result import ValidationResult, ValidatorException
from .sequential import Sequential

TYPE_DECIMAL = 'decimal'
TYPE_ENUM = 'enum'
TYPE_TIMESTAMP = 'timestamp'
TYPE_STRING = 'string'

class Field:
    def __init__(self, field):
        # extract required settings
        self.path = field.get('Path')
        if self.path is None:
            raise ValidatorException("Missing required configuration property 'Path' for field '%s'" % field)
        self.type = field.get('Type')
        if self.type is None:
            raise ValidatorException("Missing required configuration property 'Type' for field '%s'" % field)

        # extract constraints
        upper_limit = field.get('UpperLimit')
        if upper_limit is not None:
            self.upper_limit = Decimal(upper_limit)
        lower_limit = field.get('LowerLimit')
        if lower_limit is not None:
            self.lower_limit = Decimal(lower_limit)
        values = field.get('Values')
        if values is not None:
            self.values = json.loads(values)
        increment = field.get('Increment')
        if increment is not None:
            self.increment = int(increment)
        equals_value = field.get('EqualsValue')
        if equals_value is not None:
            self.equals_value = str(equals_value)

    def _get_field_value(self, data):
        try:
            path_keys = self.path.split(".")
            value = data
            for key in path_keys:
                value = value.get(key)
            return value
        except AttributeError as e:
            raise ValidatorException("Could not find field with path '%s' in message: '%s'" % (self.path, data))

    def validate(self, data):
        field_value = self._get_field_value(data)
        if field_value is None:
            return ValidationResult(False, "Field '%s' missing" % self.path)
        if field_value == "":
            return ValidationResult(False, "Field '%s' empty" % self.path)
        if hasattr(self, 'upper_limit') and Decimal(field_value) > self.upper_limit:
            return ValidationResult(False, "Field '%s' value '%d' is greater than upper limit '%d'" % (self.path, Decimal(field_value), self.upper_limit))
        if hasattr(self, 'lower_limit') and Decimal(field_value) < self.lower_limit:
            return ValidationResult(False, "Field '%s' value '%d' is less than lower limit '%d'" % (self.path, Decimal(field_value), self.lower_limit))
        if hasattr(self, 'values') and str(field_value) not in self.values:
            return ValidationResult(False, "Field '%s' value '%s' not in list of known values: [%s]" % (self.path, str(field_value), ', '.join(map(str, self.values))))
        if hasattr(self, 'equals_value') and str(field_value) != str(self.equals_value):
            return ValidationResult(False, "Field '%s' value '%s' did not equal expected value '%s'" % (self.path, field_value, self.equals_value))
        if hasattr(self, 'increment'):
            if not hasattr(self, 'previous_value'):
                self.previous_value = field_value
            else:
                if field_value != (self.previous_value + self.increment):
                    result = ValidationResult(False, "Field '%s' successor value '%d' did not match expected value '%d', increment '%d'" % (self.path, field_value, self.previous_value+self.increment, self.increment))
                    self.previous_value = field_value
                    return result
        if self.type == TYPE_TIMESTAMP:
            try:
                dateutil.parser.parse(field_value)
            except Exception as e:
                return ValidationResult(False, "Field '%s' value could not be parsed as a timestamp, error: %s" % (self.path, str(e)))
        return ValidationResult(True, "")

class TestCase:
    def __init__(self, filepath):
        assert Path(filepath).is_file(), "Configuration file '%s' could not be found" % filepath
        self.config = configparser.ConfigParser()
        self.config.read(filepath)
        self.field_list = []
        for key in self.config.sections():
            if key == "_settings":
                continue
            else:
                self.field_list.append(Field(self.config[key]))

    def _validate(self, data):
        validations = []
        for field in self.field_list:
            result = field.validate(data)
            validations.append({
                'Field': field.path,
                'Valid': result.valid,
                'Details': result.error
            })
        return validations

    def validate_queue(self, msg_queue):
        results = []
        msg_list = []
        while not msg_queue.empty():
            current_msg = json.loads(msg_queue.get())
            msg_list.append(current_msg)
            record_id = str(current_msg['metadata']['serialId']['recordId'])
            field_validations = self._validate(current_msg)
            results.append({
                'RecordID': record_id,
                'Validations': field_validations
            })

        seq = Sequential()
        sorted_list = sorted(msg_list, key=lambda msg: (msg['metadata']['logFileName'], msg['metadata']['serialId']['recordId']))

        sequential_validations = seq.perform_sequential_validations(sorted_list)
        serialized = []
        for x in sequential_validations:
            serialized.append({
                'Field': "SequentialCheck",
                'Valid': x.valid,
                'Details': x.error
            })

        results.append({
                    'RecordID': -1,
                    'Validations': serialized
                })

        return {'Results': results}

# main function using old functionality
def test():
    config_file = "samples/bsmTx.ini"
    # Parse test config and create test case
    validator = TestCase(config_file)

    print("[START] Beginning test routine referencing configuration file '%s'." % config_file)

    data_file = "samples/bsmTxGood.json"
    results = test_file(validator, data_file)
    print(results)

    data_file = "samples/bsmTxBad.json"
    results = test_file(validator, data_file)
    print(results)

# main function using old functionality
def test_file(validator, data_file):
    print("Testing '%s'." % data_file)

    with open(data_file) as f:
        content = f.readlines()

    # remove whitespace characters like `\n` at the end of each line
    content = [x.strip() for x in content]
    #msgs = [json.loads(line) for line in content]

    q = queue.Queue()
    for msg in content:
        q.put(msg)

    results = validator.validate_queue(q)

    return results

if __name__ == '__main__':
    test()