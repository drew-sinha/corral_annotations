import numpy
import pathlib
import re
import datetime
import ris_widget.ris_widget
import ris_widget.image
import PyQt5.Qt as Qt
import PyQt5.QtGui as QtGui
import glob
import pandas as pd
import gc
import sys

'''
    TODOs:
        - Maybe add add'l toolbar for referencing/displaying the current worm (typable field instead of a 'Goto' button)
        - Implement indexing for working with cleaned_directories (i.e. missing worms)
'''


class DeathDayEvaluator:
    def __init__(self, in_dir, image_glob, labels,autosave_dir=None, start_idx=0, stop_idx=None, autoload_annotations = None):
        self.rw = ris_widget.ris_widget.RisWidget()
        self._init_notefield()
        
        self.autosave_dir = pathlib.Path(autosave_dir) if autosave_dir is not None else None
        self.in_dir = in_dir
        self.labels=labels
        self.image_glob=image_glob
        self.start_idx = start_idx
        self.stop_idx = stop_idx
        self.all_images, self.worm_positions=self.parse_inputs()
        self.worm_info = pd.DataFrame(index=self.worm_positions,columns=self.labels+['Notes'])  # Add extra field for notes

        self.set_index(0)
        self.actions = []
        self._add_action('prev', Qt.Qt.Key_BracketLeft, lambda: self.load_next_worm(self.well_index,-1))    # Changed these because I tended to accidentally hit side keys
        self._add_action('next', Qt.Qt.Key_BracketRight, lambda: self.load_next_worm(self.well_index,1))
        self._add_action('Save Annotations', QtGui.QKeySequence('Ctrl+S'),self.save_annotations)
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        self._add_action('Load Annotations', QtGui.QKeySequence('Ctrl+O'),self.load_annotations)
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        self._add_action('Goto Index', QtGui.QKeySequence('Ctrl+G'), self.goto_index)
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        self.rw.show()
        
        if autoload_annotations:
            if autoload_annotations  == 'autosave':
                load_path = pathlib.Path(autosave_dir) / 'annotator_autosave.tsv'
                assert load_path.exists()
            elif autoload_annotations == 'expt':
                try:
                    load_path = pathlib.Path([expt_file for expt_file in pathlib.Path(in_dir).iterdir()
                        if '.tsv' in str(expt_file) and '~' not in str(expt_file)][0])
                except FileNotFoundError:
                    print('Couldn\'t find file')
            
            loaded_info = pd.read_csv(load_path.open(),sep='\t',index_col=0)
            if (set(loaded_info.columns.values) != set(self.worm_info.columns.values)) or (set(loaded_info.index) != set(self.worm_info.index)):
                print(loaded_info)
                print(self.worm_info)
                raise Exception('Bad annotation file')
            
            self.worm_info = loaded_info
            self.labels = list(self.worm_info.columns.values)
            # Check if defaulted to float per Pandas 
            # (occurs if no entries in Notes column in file)
            if self.worm_info['Notes'].dtype is numpy.dtype('float64'): 
                self.worm_info['Notes'] = ''  
            print('annotations read from '+str(load_path))
            self.refresh_info()

    def _init_notefield(self):  
        self.nf = NoteField(parent=self.rw.qt_object)
        self.nf_dock_w = Qt.QDockWidget('AnnotationNoteField')
        self.nf_dock_w.setWidget(self.nf)
        self.nf_dock_w.setAllowedAreas(Qt.Qt.BottomDockWidgetArea)
        self.nf_dock_w.setFeatures(Qt.QDockWidget.DockWidgetFloatable | Qt.QDockWidget.DockWidgetMovable)
        self.rw.qt_object.addDockWidget(Qt.Qt.BottomDockWidgetArea,self.nf_dock_w)

    
    def get_current_worm_position(self):
        return self.current_worm_position     
    
    def record_labeled_positions(self):
        for my_label in self.labels:
            for time_idx, flipbook_page in enumerate(self.rw.flipbook.pages):
                if flipbook_page.name == my_label: 
                    #self.dictionary[self.current_worm_position][my_label]=time_idx
                    self.worm_info.set_value(self.worm_positions[self.well_index],my_label,time_idx+self.start_idx)
        self.worm_info.set_value(self.worm_positions[self.well_index],'Notes',self.nf.get_text())
                    
        #return self.dictionary    
   
    def load_next_worm(self,index,offset):
        if index+offset not in range(len(self.worm_info)): # do nothing if trying to go out of bounds
            return
        
        if self.autosave_dir is not None:
            self.worm_info.to_csv((self.autosave_dir/'annotator_autosave.tsv').open('w'),sep='\t')
        self.record_labeled_positions()
        if(len(self.rw.flipbook.pages)>0): self.rw.flipbook.pages.clear()
        gc.collect()    # Delete this; needed it to do appropriate cleanup on my computer with old RisWidget
        
        self.set_index(index+offset)
        # Resets zoom to fit
        #~ self.rw.main_view.zoom_to_fit_action.toggle()
        

    def parse_inputs(self): 
        #subdirectories= glob.glob(self.in_dir+'/[0-9][0-9]*')
        subdirectories= glob.glob(self.in_dir+'/[0-9]*/')
        worm_positions=[]
        meow=[]
        for item in subdirectories:
            #r=re.search('\d{2,3}$', item)
            r=re.search('/\d{1,3}[/]$', item)
            #worm_positions.append(r.group())
            worm_positions.append(r.group()[:-1])   # Remove trailing '/'
            all_images=glob.glob(item+self.image_glob)
            all_images=sorted(list(map(pathlib.Path,all_images)))
            meow.append(all_images)
        print('finished parsing inputs')
        return meow, worm_positions
        

    def _add_action(self, name, key, function):
        action = Qt.QAction(name, self.rw.qt_object)
        action.setShortcut(key)
        self.rw.qt_object.addAction(action)
        action.triggered.connect(function)
        self.actions.append(action)

    def set_index(self, index):     
        self.well_index = index
        self.current_worm_position=self.worm_positions[index]
        if self.start_idx <= len(self.all_images[index]): # For the case that a given stack ends at a timepoint past the desired start_idx (e.g. a no-hatch)
            self.rw.flipbook.add_image_files(self.all_images[index][self.start_idx:self.stop_idx if self.stop_idx is not None else len(self.all_images[index])])
            self.rw.flipbook.pages_view.setFocus()
        else:
            self.rw.layer_stack.layers[0].image=None
            self.rw.image_view.setFocus() # Force the focus, else the zoom box gets the focus
        self.refresh_info()
        
    def refresh_info(self):
        # Repopulate page titles with information from worm_info
        for label in self.labels:
            LABEL_NULL = ~(self.worm_info.loc[self.worm_positions[self.well_index]].notnull())[label]
            if LABEL_NULL or label == 'Notes': continue
            
            if self.stop_idx is not None: range_stop = self.stop_idx
            else: range_stop = len(self.all_images[self.well_index])
            #print(range_stop)
            
            IDX_IN_RANGE = int(self.worm_info.loc[self.worm_positions[self.well_index]][label]) in range(self.start_idx, range_stop)
            #print(IDX_IN_RANGE)
            
            if IDX_IN_RANGE:
                self.rw.flipbook.pages[
                    int(self.worm_info.loc[self.worm_positions[self.well_index]][label])-self.start_idx].name=label
        if (self.worm_info.loc[self.worm_positions[self.well_index]].notnull())['Notes']:
            self.nf.set_text(self.worm_info.loc[self.worm_positions[self.well_index]]['Notes'])
        else:
            self.nf.set_text('NOT DEAD')
    
    def save_annotations(self):
        self.record_labeled_positions() # Grab the latest annotations
        file_dialog = Qt.QFileDialog()
        file_dialog.setAcceptMode(Qt.QFileDialog.AcceptSave)
        if file_dialog.exec_():     # Run dialog box and check for a good exit
            save_path = pathlib.Path(file_dialog.selectedFiles()[0])
            self.worm_info.to_csv(save_path.open('w'),sep='\t')
            print('file written to '+str(save_path))
    
    def load_annotations(self):
        file_dialog = Qt.QFileDialog()
        file_dialog.setAcceptMode(Qt.QFileDialog.AcceptOpen)
        if file_dialog.exec_():     # Run dialog box and check for a good exit
            load_path = pathlib.Path(file_dialog.selectedFiles()[0])
            loaded_info = pd.read_csv(load_path.open(),sep='\t',index_col=0)
            if (set(loaded_info.columns.values) != set(self.worm_info.columns.values)) or (set(loaded_info.index) != set(self.worm_info.index)):
                print(loaded_info)
                print(self.worm_info)
                raise Exception('Bad annotation file')
            
            self.worm_info = loaded_info
            self.labels = list(self.worm_info.columns.values)
            print('annotations read from '+str(load_path))
            # Check if defaulted to float per Pandas 
            # (occurs if no entries in Notes column in file)
            if self.worm_info['Notes'].dtype is numpy.dtype('float64'):
                self.worm_info['Notes'] = ''  # Force columns to be empty string if neccessary
            self.refresh_info()
    
    def goto_index(self):
        idx_dialog = Qt.QInputDialog()
        idx_dialog.setInputMode(Qt.QInputDialog.IntInput)
        idx_dialog.setIntMaximum(len(self.worm_positions)-1) # Default is 100, so need to explicitly set
        if idx_dialog.exec_():
            self.load_next_worm(idx_dialog.intValue(),0)

class NoteField(Qt.QWidget):
    '''
        Wrapper class for the QWidget that holds the notebox used in annotation
    '''
    
    def __init__(self,**kwargs):
        super().__init__(**kwargs)
        self.setFixedSize(275,90)
        self.setWindowTitle('Annotation Note Field')

        self.notebox = Qt.QLineEdit(self)
        self.notebox.move(5,5)
        self.notebox.setFixedSize(265,80)

    def run(self):
        self.show()
    
    def set_text(self,text):
        self.notebox.setText(text)
    
    def get_text(self):
        return self.notebox.text()
    
    def clear_text(self):
        self.notebox.setText('')
