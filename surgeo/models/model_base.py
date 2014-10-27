import abc
import csv
import io
import itertools
import logging
import os
import sqlite3

import surgeo

from surgeo.utilities.error_class import SurgeoError
from surgeo.calculate.weighted_mean import get_weighted_mean

###############################################################################


class BaseModel(metaclass=abc.ABCMeta):
    '''Base class for creating models.

    Attributes
    ----------
    surgeo_folder_path : string
        Path to a shared sqlite3 database connection.
    temp_folder_path : string
        Path to a folder used as a temporary holding area.
    model_folder_path : string
        Path to folder that contains models.
    logger : logging.Logger or logging.RootLogger
        Logger for the individual model.
    db_path : string
        Path to sqlite3 database.

    Methods
    -------
    build_up()
        setups up data as necessary
    db_check()
        checks db for proper table
    db_create()
        creates db tables if necessary
    db_destroy()
        removes database tables associated with this class.
    get_result_object()
        take parameters return result ProxyResult object.
    csv_summary()
        takes csv, returns summary statistic csv.
    csv_process()
        takes two paths. Reads one, writes to another.
    temp_cleanup()
        this function is used with atexit for cleanup.

    '''

    def __init__(self):
        self.surgeo_folder_path = os.path.join(os.path.expanduser('~'),
                                               '.surgeo')
        self.temp_folder_path = os.path.join(os.path.expanduser('~'),
                                             '.surgeo',
                                             'temp')
        self.db_path = os.path.join(self.surgeo_folder_path,
                                    'surgeo.sqlite')
        self.logger = logging.getLogger(__class__.__name__)
        self.build_up()

    def build_up(self):
        '''Does setup for model.'''
        pass

    @abc.abstractmethod
    def db_check(self):
        '''Checks whether the proper db tables exist.'''
        raise NotImplementedError

    @abc.abstractmethod
    def db_create(self):
        '''Downloads information from public sources and creates tables.'''
        raise NotImplementedError

    @abc.abstractmethod
    def db_destroy(self):
        '''Destroys tables prefixed with classname.'''
        raise NotImplementedError

    @abc.abstractmethod
    def get_result_object(self,
                          **kwargs):
        '''Takes arguments and generates result object.'''
        raise NotImplementedError

    @abc.abstractmethod
    def csv_summary(self,
                    **kwargs):
        '''Takes csv and returns a csv with summary data.'''
        raise NotImplementedError

    def csv_process(self,
                    filepath_in,
                    filepath_out,
                    header_tuple,
                    argument_tuple,
                    continue_on_model_fail=True):
        '''This this the public facing csv processing function.

        Parameters
        ----------
        filepath_in : string
            File path of csv from which data is read.
        filepath_out : string
            File path of csv where data is written.
        header_tuple : tuple
            Takes string args to search for in csv header.
        argument_tuple : tuple
            Takes string arguments being put in to model.
        continue_on_model_fail: boolean
            Determines with the model dies on bad data.

        Returns
        -------
        None

        Raises
        ------
        SurgeoError : surgeo.SurgeoError

        '''
        if not len(header_tuple) == len(argument_tuple):
            raise surgeo.SurgeoError('{} header elements and {} attribute '
                                     'elements. These should be equal.'
                                     .format(len(header_tuple),
                                             len(argument_tuple)))
        # Tuple key is (header index, argument index, csv_index)
        tuple_keys = []
        with open(filepath_in, 'rU') as input_csv:
            csv_reader = csv.reader(input_csv)
            row_1 = next(csv_reader)
            number_of_columns_base = len(row_1)
            # Get index for each header, create tuple 
            for tuple_index, tuple_item in enumerate(header_tuple):
                for row_index, row_item in enumerate(row_1):
                    if tuple_item.lower() == row_item.lower():
                        # header tuple and arugment tuple index are same
                        tuple_keys.append(tuple([tuple_index,
                                                 tuple_index,
                                                 row_index]))
            if len(tuple_keys) != len(header_tuple):
                raise surgeo.SurgeoError('Number of csv matches inconsistent '
                                         'with number of arguments.')
            # Go through all lines, amended lines with new data, and stage.
            # Writing to string buffer rather than file.
            line_buffer = io.StringIO()
            csv_writer = csv.writer(line_buffer)
            # Create data object based on row two to figure out csv length.
            row_2 = next(csv_reader)
            argument_dict = {}
            for tuple_key in tuple_keys:
                header_index = tuple_key[0]
                argument_index = tuple_key[1]
                argument_value = argument_tuple[argument_index]
                csv_index = tuple_key[2]
                row_value = row_2[csv_index]
                argument_dict[argument_value] = row_value
            result = self.get_result_object(**argument_dict)
            attribute_list = result.attribute_list()
            len_attribute_list = len(attribute_list)
            # Write header row first by splicing together
            chopped_header_row = row_1[:number_of_columns_base]
            header_row = [item for item in itertools.chain(chopped_header_row,
                                                           attribute_list)]
            csv_writer.writerow(header_row)
            # You already did a next() twice on the iterator, line 3
            input_csv.seek(0)
            argument_dict = {}
            for index, entry in enumerate(csv_reader, start=0):
                if index == 0:
                    continue
                for tuple_key in tuple_keys:
                    header_index = tuple_key[0]
                    argument_index = tuple_key[1]
                    argument_value = argument_tuple[argument_index]
                    csv_index = tuple_key[2]
                    row_value = entry[csv_index]
                    argument_dict[argument_value] = row_value
                try:
                    result = self.get_result_object(**argument_dict)
                    if result._error_result is True:
                        continue
                except Exception as e:
                    if continue_on_model_fail is True:
                        raise e
                    else:
                        self.logger.exception(''.join([e.__class__.__name__,
                                                       ': ',
                                                       e.__str__()]))
                result_list = result.value_list()
                # Chop row in the event that rows are a different length
                chopped_row = entry[:number_of_columns_base]
                # Splice new row together
                new_row = [item for item in
                           itertools.chain(chopped_row, result_list)]
                csv_writer.writerow(new_row)
            with open(filepath_out, 'w+') as f:
                f.write(line_buffer.getvalue())
            line_buffer.close()

    def temp_cleanup(self):
        '''This function is used with atexit to ensure cleanup.'''
        try:
            for item in os.listdir(self.temp_folder_path):
                full_path = os.path.join(self.temp_folder_path, item)
                os.remove(full_path)
        # BAD, BAD PYTHON.
        except:
            pass

