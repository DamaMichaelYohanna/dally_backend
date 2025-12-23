// FAQ Accordion Functionality
document.addEventListener('DOMContentLoaded', function () {
    const accordionButtons = document.querySelectorAll('.faq-accordion-button');

    accordionButtons.forEach(button => {
        button.addEventListener('click', function () {
            const accordionItem = this.parentElement;
            const isActive = accordionItem.classList.contains('active');

            // Close all accordion items
            document.querySelectorAll('.faq-accordion-item').forEach(item => {
                item.classList.remove('active');
            });

            // Open clicked item if it was closed
            if (!isActive) {
                accordionItem.classList.add('active');
            }
        });
    });
});
