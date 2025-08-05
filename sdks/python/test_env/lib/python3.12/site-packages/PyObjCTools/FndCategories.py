"""
A number of useful categories on Foundation classes
"""

__all__ = ()
import objc
from Foundation import NSAffineTransform


class NSAffineTransform(objc.Category(NSAffineTransform)):
    def rotateByDegrees_atPoint_(self, angle, point):
        """
        Rotate the coordinatespace ``angle`` degrees around
        ``point``.
        """
        self.rotateByDegrees_(angle)

        tf = NSAffineTransform.transform()
        tf.rotateByDegrees_(-angle)
        oldPt = tf.transformPoint_(point)
        oldPt.x -= point.x
        oldPt.y -= point.y
        self.translateXBy_yBy_(oldPt.x, oldPt.y)

    def rotateByRadians_atPoint_(self, angle, point):
        """
        Rotate the coordinatespace ``angle`` radians around
        ``point``.
        """
        self.rotateByRadians_(angle)

        tf = NSAffineTransform.transform()
        tf.rotateByRadians_(-angle)
        oldPt = tf.transformPoint_(point)
        oldPt.x -= point.x
        oldPt.y -= point.y
        self.translateXBy_yBy_(oldPt.x, oldPt.y)
