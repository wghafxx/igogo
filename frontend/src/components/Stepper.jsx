// Adapted from the React Bits Stepper (JavaScript + CSS).
import React, { Children, useLayoutEffect, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "motion/react";
import "./Stepper.css";
import { useLang } from "../lib/i18n";

export default function Stepper({ children, initialStep = 1, onStepChange = () => {},
  onFinalStepCompleted = () => {}, stepCircleContainerClassName = "", stepContainerClassName = "",
  contentClassName = "", footerClassName = "", backButtonProps = {}, nextButtonProps = {},
  backButtonText, nextButtonText, completeButtonText,
  disableStepIndicators = false, renderStepIndicator, className = "", ...rest }) {
  const { t } = useLang();
  const steps = Children.toArray(children);
  const [currentStep, setCurrentStep] = useState(initialStep);
  const [direction, setDirection] = useState(1);
  const [completing, setCompleting] = useState(false);
  const locked = useRef(false);
  const reduceMotion = useReducedMotion();
  const completed = currentStep > steps.length;
  const updateStep = (step) => {
    if (locked.current || step === currentStep || step < 1 || step > steps.length) return;
    setDirection(step > currentStep ? 1 : -1);
    setCurrentStep(step);
    onStepChange(step);
  };
  const next = async () => {
    if (locked.current || nextButtonProps.disabled) return;
    if (currentStep < steps.length) return updateStep(currentStep + 1);
    locked.current = true;
    setCompleting(true);
    try {
      // A failed save must leave the last step and all entered values visible.
      if (await onFinalStepCompleted() !== false) setCurrentStep(steps.length + 1);
    } finally { locked.current = false; setCompleting(false); }
  };
  return <div className={`rb-stepper ${className}`} {...rest}>
    <div className={`rb-stepper-card ${stepCircleContainerClassName}`}>
      <div className={`rb-stepper-indicators ${stepContainerClassName}`} aria-label={t("stepper.steps_label")}>
        {steps.map((_, i) => <React.Fragment key={i + 1}>
          {renderStepIndicator ? renderStepIndicator({ step: i + 1, currentStep, onStepClick: (step) => !disableStepIndicators && updateStep(step) }) :
            <button type="button" className="rb-stepper-indicator" aria-label={`${t("stepper.step")} ${i + 1}`} aria-current={currentStep === i + 1 ? "step" : undefined}
              disabled={disableStepIndicators || completing} onClick={() => updateStep(i + 1)} data-active={currentStep >= i + 1}>
              {currentStep > i + 1 ? <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2"><motion.path initial={{ pathLength: 0 }} animate={{ pathLength: 1 }} d="M5 13l4 4L19 7" /></svg> : currentStep === i + 1 ? <span className="rb-stepper-dot" /> : i + 1}
            </button>}
          {i < steps.length - 1 && <div className="rb-stepper-connector"><motion.div initial={false} animate={{ width: currentStep > i + 1 ? "100%" : "0%" }} transition={{ duration: reduceMotion ? 0 : 0.3 }} /></div>}
        </React.Fragment>)}
      </div>
      <div className={contentClassName}>
        <AnimatePresence initial={false} mode="wait" custom={direction}>
          {!completed && <StepContent key={currentStep} direction={direction} reduceMotion={reduceMotion}>{steps[currentStep - 1]}</StepContent>}
        </AnimatePresence>
      </div>
      {!completed && <div className={`rb-stepper-footer ${footerClassName}`}>
        {currentStep > 1 && <button {...backButtonProps} type="button" className={`m-chip ${backButtonProps.className || ""}`} disabled={completing || backButtonProps.disabled} onClick={() => updateStep(currentStep - 1)}>{backButtonText ?? t("common.back")}</button>}
        <button {...nextButtonProps} type="button" className={`m-cta rb-stepper-next ${nextButtonProps.className || ""}`} disabled={completing || nextButtonProps.disabled} onClick={next}>
          {currentStep === steps.length ? (completeButtonText ?? t("common.save")) : (nextButtonText ?? t("common.next"))}
        </button>
      </div>}
    </div>
  </div>;
}

function StepContent({ children, direction, reduceMotion }) {
  const ref = useRef(null);
  const [height, setHeight] = useState("auto");
  useLayoutEffect(() => {
    const node = ref.current;
    const measure = () => setHeight(node.offsetHeight || "auto");
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    observer?.observe(node);
    node.querySelector("input")?.focus({ preventScroll: true });
    return () => observer?.disconnect();
  }, []);
  return <motion.div className="rb-stepper-content" animate={{ height }} transition={{ duration: reduceMotion ? 0 : 0.25 }}>
    <motion.div ref={ref} custom={direction} initial={{ x: reduceMotion ? 0 : direction * 24, opacity: 0 }} animate={{ x: 0, opacity: 1 }} exit={{ x: reduceMotion ? 0 : direction * -24, opacity: 0 }} transition={{ duration: reduceMotion ? 0 : 0.18 }}>{children}</motion.div>
  </motion.div>;
}

export function Step({ children }) { return <div className="rb-stepper-step">{children}</div>; }
