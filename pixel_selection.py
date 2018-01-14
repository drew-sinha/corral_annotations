from PyQt5 import Qt, QtWidgets, QtGui
import pathlib
from ris_widget import ris_widget
import numpy as np
import enum
import json
import glob

'''
PixelSelection - 
    attr:
        x,y position (w,h = 1)
        parent_item (will be rw window supplied on creation
    
    init:
        object properties altered to have no fill and bolded outline.
    
PixelSelector - 
    image_dir
    selections (Nx2 array with space for pixel locations; [None,None] if no selection)
    
    init:
        Populate flipbook with images
        Link up signals for keypress/mouse events
    
    event catch:
        if delete key:
            delete object
        else click point:
            if point exists for page:
                delete old point
            make point there
    
    check_points_for_empty
    save_points, load_points
        
    

'''

class Rect_Colors(enum.Enum):
    PREV = QtGui.QColor(255,0,0)
    CURRENT = QtGui.QColor(0,255,0)
    NEXT = QtGui.QColor(0,0,255)

class PixelSelector:
    def __init__(self, image_dir, image_glob, show_contig_times=True):
        self.image_dir = pathlib.Path(image_dir)
        self.image_glob = image_glob
        self.show_contig_times = show_contig_times
        
        image_files = sorted(list(
            glob.glob(str(self.image_dir / self.image_glob))))
        
        self.rw = ris_widget.RisWidget()
        self.rw.add_image_files_to_flipbook(image_files)
        self.rw.image_view.mouse_release.connect(self.record_selection)
        self.rw.flipbook.pages_view.selectionModel().currentRowChanged.connect(self.refresh_scene) # Redraw selection rectangles while browsing through flipbook
        
        self.actions = []
        self._add_action('Save Selections', QtGui.QKeySequence('Ctrl+S'),self.save_annotations)
        self.rw.qt_object.main_view_toolbar.addAction(self.actions[-1])
        
        # Create array for populating point objects and corresponding rect
        self.selected_pos = [[-1,-1]]*len(image_files)
        self.selection_rects = [None]*len(image_files)
    
    def record_selection(self,pos):
        x, y = pos.x(), pos.y() # in image coordinates
        
        if self.selection_rects[self.rw.flipbook.current_page_idx] is None:
            qp = QtGui.QPen(Rect_Colors['CURRENT'].value)
            qp.setCosmetic(True)
            self.selection_rects[self.rw.flipbook.current_page_idx] = self.rw.image_scene.addRect(int(x),int(y),1,1,
                pen=qp)
        else:
            self.selection_rects[self.rw.flipbook.current_page_idx].setRect(int(x), int(y), 1, 1)
            
        self.selected_pos[self.rw.flipbook.current_page_idx] = [int(x), int(y)]
        
    def refresh_scene(self):
        [self.rw.image_scene.removeItem(item)
            for item in self.rw.image_view.items()
            if type(item) is QtWidgets.QGraphicsRectItem]
        
        for pg_offset, rect_color in zip([-1,0,1], Rect_Colors):
            if (self.rw.flipbook.current_page_idx + pg_offset 
                not in range(len(self.selection_rects))):
                    continue
            rect = self.selection_rects[
                self.rw.flipbook.current_page_idx + pg_offset]
            if rect is not None and (pg_offset == 0 or self.show_contig_times):
                rp = rect.pen()
                rp.setColor(rect_color.value)
                rect.setPen(rp)
                self.rw.image_scene.addItem(rect)
    
    def load_annotations(self):
        file_dialog = Qt.QFileDialog()
        file_dialog.setAcceptMode(Qt.QFileDialog.AcceptOpen)
        if file_dialog.exec_():     # Run dialog box and check for a good exit
            load_path = pathlib.Path(file_dialog.selectedFiles()[0])
            loaded_info = json.load(load_path.open('r'))
            if self.image_dir != loaded_info['image_dir']:
                print(loaded_info)
                print(self.worm_info)
                raise Exception('Bad selection annotation file')
            
            self.selected_pos = loaded_info['selected_pos']
            
            qp = QtGui.QPen(Rect_Colors['CURRENT'].value)
            qp.setCosmetic(True)
            self.selection_rects = [self.rw.image_scene.addRect(int(x),int(y),1,1,
                pen=qp) for (x,y) in self.selected_pos]
            self.refresh_scene()
            print('annotations read from '+str(load_path))
    
    
    def save_annotations(self):
        file_dialog = Qt.QFileDialog()
        file_dialog.setAcceptMode(Qt.QFileDialog.AcceptSave)
        if file_dialog.exec_():     # Run dialog box and check for a good exit
            save_data = {'selected_pos': self.selected_pos,
                 'image_dir': str(self.image_dir)}
            
            save_path = pathlib.Path(file_dialog.selectedFiles()[0])
            encode_legible_to_file(save_data, save_path.open('w'))
            print('file written to '+str(save_path))
        
    def _add_action(self, name, key, function):
        action = Qt.QAction(name, self.rw.qt_object)
        action.setShortcut(key)
        self.rw.qt_object.addAction(action)
        action.triggered.connect(function)
        self.actions.append(action)
        

# Swiped from zplab.rpc_acquisition....json_encode
class Encoder(json.JSONEncoder):
    """JSON encoder that is smart about converting iterators and numpy arrays to
    lists, and converting numpy scalars to python scalars.
    Caution: it is absurd to send large numpy arrays over the wire this way. Use
    the transfer_ism_buffer tools to send large data.
    """
    def default(self, o):
        try:
            return super().default(o)
        except TypeError as x:
            if isinstance(o, np.generic):
                item = o.item()
                if isinstance(item, npy.generic):
                    raise x
                else:
                    return item
            try:
                return list(o)
            except:
                raise x


COMPACT_ENCODER = Encoder(separators=(',', ':'))
READABLE_ENCODER = Encoder(indent=4, sort_keys=True)

def encode_compact_to_bytes(data):
    return COMPACT_ENCODER.encode(data).encode('utf8')

def encode_legible_to_file(data, f):
    for chunk in READABLE_ENCODER.iterencode(data):
        f.write(chunk)


'''
    def record_selection(self,pos):
        print(pos)
        x, y = pos.x(), pos.y() # in image coordinates
        print(int(x),int(y))
        
        rect_items = [item for item in self.rw.image_view.items()
            if type(item) is QtWidgets.QGraphicsRectItem]
            
        print(rect_items)
        if len(rect_items) == 0:
            qp = QtGui.QPen(QtGui.QColor(255,0,0))
            qp.setCosmetic(True)
            qr = self.rw.image_scene.addRect(int(x),int(y),1,1,
                pen=qp)
        else:
            # Assume the rect is at the top of the stack.
            rect_items[0].setRect(int(x), int(y), 1, 1)
            
        self.selected_pos[self.rw.flipbook.selected_page_idxs[0],:] = [int(x), int(y)]
        '''

'''
# This event adds a single rectangle to the scene and moves it with add'l clicks.
    def mouse_release(self, pos):
        x, y = self.x(), self.y() # in image coordinates
        print(int(x),int(y))
        
        rect_items = [item for item in rw.image_view.items()
            if type(item) is QtWidgets.QGraphicsRectItem]
            # Assume the rect is at the top of the stack.
            
        print(rect_items)
        if len(rect_items) == 0:
            qp = QtGui.QPen(QtGui.QColor(255,0,0))
            qp.setCosmetic(True)
            qr = rw.image_scene.addRect(int(x),int(y),1,1,
                pen=qp)
        else:
            rect_items[0].setRect(int(x),int(y),1,1)

'''

'''
Other examples of working with Qt....

    def mouse_release(self, pos):
        x, y = self.x(), self.y() # in image coordinates
        print(int(x),int(y))
        qp = QtGui.QPen(QtGui.QColor(255,0,0))
        qp.setCosmetic(True)
        qr = rw.image_scene.addRect(int(x),int(y),1,1,
            pen=qp)
            
        qr = rw.image_scene.addRect(int(x),int(y),10,10,
            pen=QtGui.QPen(QtGui.QColor(255,0,0)),
            brush=QtGui.QBrush(QtGui.QColor(0,255,0)))
        
        qr = QtWidgets.QGraphicsRectItem(int(x),int(y),1,1)
        rw.image_scene.addItem(qr)
        qr_inside = QtWidgets.QGraphicsRectItem(int(x)+0.2,int(y)+0.2,0.6,0.6)
        rw.image_scene.addItem(qr_inside)
        if qr is None: 
            qr = QtGui.QGraphicsRectItem(int(x),int(y),1,1,scene=rw.image_scene)
        else:
            qr.setRect(int(x),int(y),1,1)
    
    def sceneEventFilter(self, watched, event):
        if watched is self.rw.image_scene:
            if event.type() == Qt.QEvent.GraphicsSceneMouseRelease:
                record_selection(event.pos)
'''
