# -*- coding: utf-8 -*-

# Form implementation generated from reading ui file 'list_item_widget.ui'
#
#      by: pyside-uic 0.2.15 running on PySide 1.2.2
#
# WARNING! All changes made in this file will be lost!

from tank.platform.qt import QtCore, QtGui

class Ui_ListItemWidget(object):
    def setupUi(self, ListItemWidget):
        ListItemWidget.setObjectName("ListItemWidget")
        ListItemWidget.resize(426, 120)
        self.horizontalLayout_3 = QtGui.QHBoxLayout(ListItemWidget)
        self.horizontalLayout_3.setSpacing(1)
        self.horizontalLayout_3.setContentsMargins(8, 4, 8, 4)
        self.horizontalLayout_3.setObjectName("horizontalLayout_3")
        self.box = QtGui.QFrame(ListItemWidget)
        self.box.setFrameShape(QtGui.QFrame.NoFrame)
        self.box.setObjectName("box")
        self.horizontalLayout = QtGui.QHBoxLayout(self.box)
        self.horizontalLayout.setObjectName("horizontalLayout")
        self.thumbnail = QtGui.QLabel(self.box)
        self.thumbnail.setMinimumSize(QtCore.QSize(35, 35))
        self.thumbnail.setMaximumSize(QtCore.QSize(75, 75))
        self.thumbnail.setFrameShape(QtGui.QFrame.NoFrame)
        self.thumbnail.setText("")
        self.thumbnail.setPixmap(QtGui.QPixmap(":/res/sg_logo.png"))
        self.thumbnail.setScaledContents(True)
        self.thumbnail.setAlignment(QtCore.Qt.AlignCenter)
        self.thumbnail.setObjectName("thumbnail")
        self.horizontalLayout.addWidget(self.thumbnail)
        self.body = QtGui.QLabel(self.box)
        sizePolicy = QtGui.QSizePolicy(QtGui.QSizePolicy.Preferred, QtGui.QSizePolicy.Expanding)
        sizePolicy.setHorizontalStretch(0)
        sizePolicy.setVerticalStretch(0)
        sizePolicy.setHeightForWidth(self.body.sizePolicy().hasHeightForWidth())
        self.body.setSizePolicy(sizePolicy)
        self.body.setAlignment(QtCore.Qt.AlignLeading|QtCore.Qt.AlignLeft|QtCore.Qt.AlignVCenter)
        self.body.setWordWrap(True)
        self.body.setObjectName("body")
        self.horizontalLayout.addWidget(self.body)
        self.package_btn = QtGui.QPushButton(self.box)
        self.package_btn.setMinimumSize(QtCore.QSize(0, 0))
        self.package_btn.setObjectName("package_btn")
        self.horizontalLayout.addWidget(self.package_btn)
        self.horizontalLayout_3.addWidget(self.box)

        self.retranslateUi(ListItemWidget)
        QtCore.QMetaObject.connectSlotsByName(ListItemWidget)

    def retranslateUi(self, ListItemWidget):
        ListItemWidget.setWindowTitle(QtGui.QApplication.translate("ListItemWidget", "Form", None, QtGui.QApplication.UnicodeUTF8))
        self.body.setText(QtGui.QApplication.translate("ListItemWidget", "Title: To Vendor", None, QtGui.QApplication.UnicodeUTF8))
        self.package_btn.setText(QtGui.QApplication.translate("ListItemWidget", "Package", None, QtGui.QApplication.UnicodeUTF8))

from . import resources_rc
