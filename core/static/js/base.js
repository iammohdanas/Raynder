
        function dismissToast(btn) {
            const toast = btn.closest('.premium-toast');
            if (!toast) return;
            toast.classList.add('toast-hiding');
            setTimeout(() => {
                toast.remove();
            }, 250);
        }

        // Auto-dismiss after 6 seconds
        document.addEventListener('DOMContentLoaded', () => {
            const toasts = document.querySelectorAll('.premium-toast');
            toasts.forEach((toast) => {
                setTimeout(() => {
                    if (toast && toast.parentElement) {
                        toast.classList.add('toast-hiding');
                        setTimeout(() => toast.remove(), 250);
                    }
                }, 6000);
            });
        });
