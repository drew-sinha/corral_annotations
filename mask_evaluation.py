from ris_widget.ris_widget import RisWidget
from PyQt5 import Qt, QtGui
import pathlib
import pandas as pd
import re
import numpy as np
import freeimage
from corral_annotations.annotator import NoteField
import gc

import zplib.image.mask as zplib_image_mask


class MaskEditor:
    def __init__(self,expt_dir):
        '''
            expt_dir - superfolder for experiment
        '''
        self.rw = RisWidget()
        layout = Qt.QFormLayout()
        ME_widget = Qt.QWidget()
        ME_widget.setLayout(layout)
        
        self.edit = Qt.QPushButton("Edit Mask")
        layout.addRow(self.edit)
        self.nf = NoteField(parent=self.rw.qt_object)
        layout.addRow(self.nf)
        self.rw.flipbook.layout().addWidget(ME_widget)
        
        self.edit.clicked.connect(self._on_edit_clicked)
        self.rw.flipbook.pages_view.selectionModel().currentRowChanged.connect(self._on_page_change)
        
        self.file_globs = ['*bf.png', '*mask.png']
        self.expt_dir = pathlib.Path(expt_dir)
        self.work_dir = self.expt_dir/'work_dir'   # Super folder for masks
        self.all_images, self.worm_positions = self.parse_inputs()
        
        self.editing = False
        self.working_file = None
        self.current_page = None
        
        # Search for annotation tsv
        tsvs = list(self.expt_dir.glob('*.tsv'))
        if len(tsvs) > 1: print('Warning: More than one tsv found')
        if len(tsvs)>0:
            self.ann_fpath = tsvs[0]
        else:
            print('Warning: no tsv found')
            self.ann_fpath = None
        self.load_annotations()
        
        self.set_index(0)
        self.actions = []
        self._add_action('prev_worm', Qt.Qt.Key_BracketLeft, lambda: self.load_next_worm(self.well_index,-1))    # Changed these because I tended to accidentally hit side keys
        self._add_action('next_worm', Qt.Qt.Key_BracketRight, lambda: self.load_next_worm(self.well_index,1))
        self._add_action('Edit Mask', QtGui.QKeySequence('Ctrl+E'),self._on_edit_clicked)
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        self._add_action('Goto Worm', QtGui.QKeySequence('Ctrl+G'),self.goto_label)
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        self._add_action('Reload Masks', QtGui.QKeySequence('Ctrl+R'),lambda: self.load_next_worm(self.well_index,0))   # TODO Fix.
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        
        self.rw.show()
    
    def _add_action(self, name, key, function):
        action = Qt.QAction(name, self.rw.qt_object)
        action.setShortcut(key)
        self.rw.qt_object.addAction(action)
        action.triggered.connect(function)
        self.actions.append(action)
    
    def parse_inputs(self): 
        worm_positions=[]
        compiled_images={file_glob:[] for file_glob in self.file_globs}
        for subdir in list(self.work_dir.iterdir()): 
            if subdir.is_dir():
                r=re.search('\d{1,3}[/]?$', str(subdir))    # For post processed images....
                worm_positions.append(('/'+r.group()))           
                for file_glob in compiled_images.keys():
                #~ if 'mask' in file_glob:
                    #~ compiled_images[file_glob].append(subdir.glob(file_glob))
                    
                #~ else:
                    #~ compiled_images[file_glob].append((self.expt_dir/subdir.parts[-1]).glob(file_glob))
                    compiled_images[file_glob].append(sorted(subdir.glob(file_glob)))   # Assuming bf images in same directory
        #compiled_images=sorted(compiled_images)        
        print('finished parsing inputs')
        return compiled_images, worm_positions
    
    def load_annotations(self):
        if self.ann_fpath is not None:
            loaded_info = pd.read_csv(self.ann_fpath.open(),sep='\t',index_col=0)
            # Sift through and only keep references to kept worms
            to_drop = []
            for worm in loaded_info.index:
                if worm not in self.worm_positions: 
                    to_drop.append(worm)
            self.worm_info = loaded_info.drop(to_drop)
            print('annotations read from '+str(self.ann_fpath))
    
    def set_index(self, index):
        self.well_index = index
        self.current_worm_position=self.worm_positions[index]
        self.rw.flipbook.add_image_files([
            my_pics for my_pics in zip(*[self.all_images[file_glob][index] for file_glob in self.file_globs])])
        self.refresh_info()
    
    def refresh_info(self):
        if self.ann_fpath is not None:
            # Repopulate page titles with information from worm_info
            for label in self.worm_info.keys():
                if label != 'Notes' and (self.worm_info.loc[self.worm_positions[self.well_index]].notnull())[label]:
                    self.rw.flipbook.pages[
                        int(self.worm_info.loc[self.worm_positions[self.well_index]][label])].name=label
            if (self.worm_info.loc[self.worm_positions[self.well_index]].notnull())['Notes']:
                print((self.worm_info.loc[self.worm_positions[self.well_index]].notnull())['Notes'])
                self.nf.set_text(self.worm_info.loc[self.worm_positions[self.well_index]]['Notes'])
            else:
                self.nf.set_text('')
    
    def load_next_worm(self,index,offset):
        #if self.editing: self.stop_editing(save_work=(offset is not 0)) # Pass this argument to prevent saving when trying to refresh masks from images
        if(len(self.rw.flipbook.pages)>0): 
            self.rw.flipbook.pages.clear()
            gc.collect()
        if self.all_images[self.file_globs[0]][index+offset]:
            self.set_index(index+offset)
    
    def _on_page_change(self):
        if self.current_page is not None:
            self.current_page.inserted.disconnect(self._on_page_change)
            if self.editing:
                self.stop_editing()
        
        # Repopulate current page data
        self.current_page = self.rw.flipbook.focused_page
        if self.current_page is None:
            return
        self.current_page.inserted.connect(self._on_page_change)
        if len(self.current_page) == 0:
            self.old_well = None
            return
        self.current_page[1].set(data=self.current_page[1].data.astype(bool))
    
    def _on_edit_clicked(self):
        if self.editing:
            self.stop_editing()
        else:
            self.start_editing()
            
    def start_editing(self):        
        #Do everything in second layer; will need to modify Willie's code for worm measurement
        self.editing = True
        self.working_file = pathlib.Path(self.rw.layers[1].image.name)
        self.edit.setText('Save Edits')
        
        # Bring focus to mask layer
        sm = self.rw.qt_object.layer_stack._selection_model
        m = sm.model()
        sm.setCurrentIndex(m.index(0,0),
            Qt.QItemSelectionModel.SelectCurrent|Qt.QItemSelectionModel.Rows)
        
        self.rw.layers[1].opacity = 0.5
        self.rw.layers[1].tint = (1.0,0,0,1.0)
        self.rw.qt_object.layer_stack_painter_dock_widget.show()
        self.rw.qt_object.layer_stack_painter.brush_size_lse.value = 13
        self.current_page[1].set(data=(self.current_page[1].data*0).astype('bool'))
        
        
    def stop_editing(self,save_work=True):
        # Convert outline to mask 
        outline = zplib_image_mask.get_largest_object(
            self.rw.layers[1].image.data>0)
        new_mask = zplib_image_mask.fill_small_area_holes(outline,300000).astype('uint8')
        new_mask[new_mask>0] = -1
        self.rw.layers[1].image.set(data=(new_mask>0).astype('bool'))
        self.rw.layers[1].tint = (1.0,1.0,1.0,1.0)
        
        self.rw.qt_object.layer_stack_painter_dock_widget.hide()
        if self.current_page[1].data.any():
            if not pathlib.Path(str(self.working_file).replace('mask.png','mask_oldwf.png')).exists():
                self.working_file.rename(str(self.working_file).replace('mask.png','mask_oldwf.png'))
            freeimage.write(new_mask, self.working_file)
        
        self.editing = False
        self.working_file = None    # Do this after saving out since need the working file above
        self.edit.setText('Edit Mask')
    
    def goto_label(self):
        idx_dialog = Qt.QInputDialog()
        idx_dialog.setInputMode(Qt.QInputDialog.TextInput)
        if idx_dialog.exec_() and idx_dialog.textValue() in self.worm_info.index:
            self.load_next_worm(self.worm_info.index.get_loc(idx_dialog.textValue()),0)