'''
    annotation_file.py
    Contains an interface for interacting with and extracting data out of annotation tsv files
'''

import numpy as np
import json
import pandas as pd
import pathlib

def find_char(string,ch):
    '''
        Pulls out positions for a particular character in a string
    '''
    return [idx for (idx, letter) in enumerate(string) if letter == ch]

class AnnotationFile:
    def __init__(self, input_data, annotation_prefix=''):
        '''
            Arguments:
                input_data - str/pathlib.Path or pd.DataFrame compatible structure providing data to add to file
                annotation_prefix - character to add to front of annotation; used for annotations coming from multiple experiments/metadata files
        '''
        if type(input_data) is str or type(input_data) is pathlib.Path:
            self.data = pd.read_table(input_data,dtype=str)
        else:   # Assume compatible with pandas DataFrame
            self.data = pd.DataFrame(input_data,dtype=str)
        self.data.fillna('')  # NOTE! Data is internally stored as an object of str's!
        
        if annotation_prefix != '':
            for tag in self.data.keys():
                if tag not in ['Notes','Worm']:
                    for row_idx, val in zip(self.data[tag].index, self.data[tag]):
                        if val != '' and not val[0].isalpha():
                            self.data.set_value(row_idx,tag,annotation_prefix+val)
        
        
    def raw_data(self, expt_name='',restricted_list=None):
        '''
            Pass back raw_data from this object while potentially adding a field for the worm's full designation
        '''
        
        raw_data = self.data.copy()
        if expt_name != '':
            raw_data.loc[:,'Worm_FullName'] = pd.Series(
                np.array([expt_name+' '+worm_name[1:] for worm_name in raw_data['Worm']]))
        if restricted_list is None:
            return raw_data
        else:
            return raw_data.loc[restricted_list]
        
        
    def data_as_timestamps(self, metadata_list, expt_name='',restricted_list=None,as_timepoints=False):
        '''
            Pass back data in timed format using frame numbers from annotation file/data
            
            Arguments:
            metadata_list: (character delimiter: experiment metadata file paths)
            expt_name: Optional string identifying this experiment
            restricted_list (numpy array suitable for indexing) - list for grabbing data from a specific set of worms
            as_timepoints: Flag to pass back data as either hours post-expt start (False) or datetime string (True)
            
            Returns:
            out_data: timestamps (-1 replaces any field that is left empty)
        '''
        out_data = self.data.copy()
        
        metadata_info = {}
        for metadata_pair in metadata_list.items():
            with open(metadata_pair[1]) as metadata_fp:
                metadata_info[metadata_pair[0]] = json.load(metadata_fp)
        
        for a_tag in out_data.keys():
            if a_tag not in ['Notes', 'Worm']:
                    if not as_timepoints:
                        out_data[a_tag] = \
                            np.array(
                            [metadata_info[time_idx[0]]['timestamps'][int(time_idx[1:])]-metadata_info[time_idx[0]]['timestamps'][0] if time_idx != '' else -1 for time_idx in out_data[a_tag]])
                    else:
                        out_data[a_tag] = \
                            np.array(
                            [metadata_info[time_idx[0]]['timepoints'][int(time_idx[1:])] if time_idx != '' else '-1' for time_idx in out_data[a_tag]])
                    
        if expt_name is not '':
            out_data['Worm_FullName'] = np.array([expt_name+' '+worm_name[1:] for worm_name in out_data['Worm']])
        
        if restricted_list is None:
            return out_data
        else:
            return out_data.loc[restricted_list]


    def data_as_timestamps_simple(self, metadata_file,expt_name='', restricted_list=None, as_timepoints=False):
        '''
            Returns each set of data in the 'data' field as times relative to the start of the experiment (IN SECONDS)
            
            ARGUMENTS:
                metadata_file (string) - Corresponding metadata file to use that relates each frame number from the annotation to an actual data/time
                expt_name: Optional string identifying this experiment
                restricted_list (numpy array suitable for indexing) - list for grabbing data from a specific set of worms
                as_timepoints: Flag to pass back data as either hours post-expt start (False) or datetime string (True)
        '''
        
        out_data = self.data.copy()
        
        with open(metadata_file) as metadata_fp:
            metadata_info = json.load(metadata_fp)
        
        # For each column in tsv,
        for a_tag in out_data.keys():
            out_data[a_tag][out_data[a_tag]=='']='-1'   # Empty field gets '-1'
            if a_tag != 'Notes' and a_tag != 'Worm':    # If not the non-time fields
                if not as_timepoints:
                    out_data[a_tag]=np.array([metadata_info['timestamps'][int(time_idx)]-metadata_info['timestamps'][0] for time_idx in out_data[a_tag]])
                    out_data[a_tag][self.data[a_tag]=='']=-1
                else:
                    out_data[a_tag]=np.array([metadata_info['timepoints'][int(time_idx)] for time_idx in out_data[a_tag]])
                    out_data[a_tag][self.data[a_tag]=='']='-1'
                    
        
        if expt_name is not '':
            out_data['Worm_FullName'] = np.array([expt_name+' '+worm_name[1:] for worm_name in out_data['Worm']])

        if restricted_list is None:
            return out_data
        else:
            return out_data[restricted_list]
    
    def get_goodworms(self, bad_worm_kws=[], restrict_to_hatched=False, expt_path=None):
        '''
            Find all of the good worms based on annotation data
            
            Arguments:
                bad_worm_kws - array of kws used to filter out bad worms
                restrict_to_hatched - flag to filter out animals that were hatched at the first timepoint
                expt_path - path to experiment used when one wants to use acquisition information from the experiment to filter out animals
            
            Returns:
                goodworms - boolean array where True indicates a good worm
        
        '''
        
        if len(bad_worm_kws) is 0:   # Use DEAD as marker
            viable_worm = (self.data['Hatch']!='') \
                & (self.data['Death']!='') \
                & np.array([('DEAD' in note and not 'NEVER LAID EGGS' in note) for note in self.data['Notes']])
        else:
            viable_worm = (self.data['Hatch']!='') \
                & (self.data['Death']!='') \
                & np.array([not any([kw in note for kw in bad_worm_kws]) for note in self.data['Notes']])
        
        goodworms = viable_worm #& worm_was_acquired
        if expt_path is not None:   # Need to screen for wells that weren't acquired (i.e. deleted)
            from process_data import Experiment
            
            first_worm_num = int(self.data['Worm'][0][-2:])   # Add in adjustment for the first index of the worms not being at 0
            expt = Experiment(expt_path)
            worm_was_acquired = [str(worm_num+first_worm_num).zfill(len(expt.get_acquired_wells()[0])) in expt.get_acquired_wells() for worm_num in np.arange(len(self.data['Hatch']))]
        
        if restrict_to_hatched: goodworms = goodworms & (self.data['Hatch'] !=0)
        
        return goodworms
    
    def get_skip_positions(self,bad_worm_kws=[]):
        '''
            Handy tool for getting skip positions from annotation_data
            
            Returns:
                List of strings that can directly be placed into (experiment_metadata) json
        '''
        
        good_worms = self.get_goodworms(bad_worm_kws=bad_worm_kws)
        dead_worms = np.array(['NOT DEAD' not in note for note in self.data['Notes']])
        skip_idxs = np.where((not good_worms)|dead_worms)[0][0]
        return [str(idx).zfill(len(self.data['Worm'][0].index)) for idx in skip_idxs]
    
    def save_timestamp_tsv(self, output_file):        
        if type(output_file) is not pathlib.Path:
            output_file = pathlib.Path(output_file)
        
        with output_file('w').open() as output_fp:
            self.data_as_timestamps(metadata_args).to_csv(sep='\t')

def compile_expt_timestamped_data(expt_dirs, md_dict=None,as_timepoints=False):
    '''
        Builds super-table of timestamped data from multiple experiments
    '''
    
    timestamped_data = {}
    if md_dict is None:
        for expt_dir in expt_dirs: 
            ann_file = AnnotationFile(
                [expt_dir+os.path.sep+my_file for my_file in sorted(os.listdir(expt_dir)) if '.tsv' in my_file][0])
            if expt_dir[-1] is not os.path.sep:
                expt_name = expt_dir[find_char(expt_dir,os.path.sep)[-1]:]
            else:
                expt_name = expt_dir[find_char(expt_dir,os.path.sep)[-2]:-1]
            ann_file_data = ann_file.data_as_timestamps_simple(expt_dir+os.path.sep+'experiment_metadata.json',restricted_list=ann_file.get_goodworms(),expt_name=expt_name,as_timepoints=as_timepoints)
            timestamped_data.append(ann_file_data)
    else:
        for expt_dir, md_map in zip(expt_dirs, md_dict):
            if expt_dir[-1] is not os.path.sep:
                expt_name = expt_dir[find_char(expt_dir,os.path.sep)[-1]:]
            else:
                expt_name = expt_dir[find_char(expt_dir,os.path.sep)[-2]:-1]

            if list(md_map.keys())[0] is '':
                ann_file = AnnotationFile(
                    [expt_dir+os.path.sep+my_file for my_file in sorted(os.listdir(expt_dir)) if '.tsv' in my_file and 'lock' not in my_file][0])
                ann_file_data = ann_file.data_as_timestamps_simple(expt_dir+os.path.sep+'experiment_metadata.json',restricted_list=ann_file.get_goodworms(),expt_name=expt_name,as_timepoints=as_timepoints)
            else:
                ann_file = AnnotationFile(
                    [expt_dir+os.path.sep+my_file for my_file in sorted(os.listdir(expt_dir)) if '.tsv' in my_file and 'lock' not in my_file][0],
                    annotation_prefix='D')
                ann_file_data = ann_file.data_as_timestamps(md_map,restricted_list=ann_file.get_goodworms(),expt_name=expt_name, as_timepoints=as_timepoints)
            timestamped_data = timestamped_data.append(ann_file_data)
    timestamped_data[np.isnan(timestamped_data)]=-1
    return timestamped_data

def compile_expt_raw_data(expt_dirs):
    '''
        Builds super-table of timestamped data from multiple experiments
    '''
    
    raw_data = pd.DataFrame()
    for expt_dir in expt_dirs:
        ann_file = AnnotationFile(
            [expt_dir+os.path.sep+my_file for my_file in sorted(os.listdir(expt_dir)) if '.tsv' in my_file][0])
        if expt_dir[-1] is not os.path.sep:
            expt_name = expt_dir[find_char(expt_dir,os.path.sep)[-1]:]
        else:
            expt_name = expt_dir[find_char(expt_dir,os.path.sep)[-2]:-1]
        # Get data
        ann_file_data = ann_file.raw_data(expt_name=expt_name,restricted_list=ann_file.get_goodworms())
        raw_data = raw_data.append(ann_file_data)
    raw_data[np.isnan(raw_data)]=-1 # Replace hanging entries for columns not contained in an experiment with -1
    return raw_data

def write_annotation_data(data,output_file):
    '''
        data - pandas Dataframe
        output_file - path for the output file
    '''
    data.to_tsv(output_file,sep='\t')
