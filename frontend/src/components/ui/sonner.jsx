import { Toaster as Sonner, toast } from "sonner"
import { CircleCheck, CircleAlert, Info, TriangleAlert, LoaderCircle } from "lucide-react"

const icon = (Icon, cls) => <span className={`toast-icon ${cls}`}><Icon size={15} strokeWidth={2.4} /></span>

const Toaster = (props) => (
  <Sonner
    theme="dark"
    className="toaster group"
    icons={{
      success: icon(CircleCheck, "toast-icon-ok"),
      error: icon(CircleAlert, "toast-icon-err"),
      info: icon(Info, "toast-icon-info"),
      warning: icon(TriangleAlert, "toast-icon-warn"),
      loading: icon(LoaderCircle, "toast-icon-info animate-spin"),
    }}
    toastOptions={{
      unstyled: true,
      classNames: {
        toast: "blox-toast animate__animated animate__fadeInDown animate__faster",
        title: "blox-toast-title",
        description: "blox-toast-desc",
        actionButton: "blox-toast-action",
        cancelButton: "blox-toast-cancel",
        closeButton: "blox-toast-close",
      },
    }}
    {...props} />
)

export { Toaster, toast }
