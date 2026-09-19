import React, { useRef, forwardRef } from "react";

// Wraps an animated lucide icon so hovering the whole button triggers the animation
const AnimButton = forwardRef(({ icon: Icon, size = 16, className = "", iconClassName = "", iconProps = {}, children, onMouseEnter, onMouseLeave, ...props }, ref) => {
  const iconRef = useRef(null);
  return (
    <button
      ref={ref}
      className={className}
      onMouseEnter={(e) => {
        iconRef.current?.startAnimation();
        onMouseEnter && onMouseEnter(e);
      }}
      onMouseLeave={(e) => {
        iconRef.current?.stopAnimation();
        onMouseLeave && onMouseLeave(e);
      }}
      {...props}
    >
      <Icon ref={iconRef} size={size} className={`flex items-center ${iconClassName}`} {...iconProps} />
      {children}
    </button>
  );
});
AnimButton.displayName = "AnimButton";

export default AnimButton;
