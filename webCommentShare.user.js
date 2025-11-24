// ==UserScript==
// @name         REDNote web comment share link with xsec_token
// @namespace    http://tampermonkey.net/
// @version      2025-11-21
// @description  Add a copy link button to comments
// @author       Franc Gossin
// @match        https://www.xiaohongshu.com/*
// @icon         data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==
// @grant        none
// ==/UserScript==

(function() {
    'use strict';

    function addShareButtons() {
        document.querySelectorAll('.comment-item').forEach((e) => {
            // Prevent adding the button multiple times to the same comment
            if (e.dataset.hasShareBtn) return;

            // Extract Comment ID
            var commentId = e.id.split('-')[1];
            
            // Find the interactions container (where Like and Reply buttons are)
            var interactions = e.querySelector('.interactions');

            if (interactions) {
                // Create the button element
                var btn = document.createElement('div');
                btn.className = 'share-link-btn';
                // Style to match the existing UI (gray text, aligned)
                btn.style.cssText = 'display: flex; align-items: center; margin-left: 16px; cursor: pointer; font-size: 12px; color: var(--color-secondary-label, #999);';
                btn.innerHTML = '<span style="margin-right: 4px;">🔗</span>Link';

                // Add click event
                btn.onclick = function() {
                    // Construct URL safely (handles ? or & automatically)
                    var url = new URL(window.location.href);
                    url.searchParams.set('anchorCommentId', commentId);
                    
                    // Copy to clipboard
                    navigator.clipboard.writeText(url.toString()).then(() => {
                        // Visual feedback
                        var originalHtml = btn.innerHTML;
                        btn.innerHTML = '<span style="margin-right: 4px;">✅</span>Copied';
                        btn.style.color = '#333'; // Darker color for feedback
                        
                        setTimeout(() => {
                            btn.innerHTML = originalHtml;
                            btn.style.color = 'var(--color-secondary-label, #999)';
                        }, 2000);
                    }).catch(err => {
                        console.error('Failed to copy: ', err);
                    });
                };

                // Add button to the container
                interactions.appendChild(btn);
                
                // Mark this comment as processed
                e.dataset.hasShareBtn = 'true';
            }
        });
    }

    // Run immediately for comments already on page
    addShareButtons();

    // Watch for new comments being loaded (infinite scroll)
    const observer = new MutationObserver((mutations) => {
        addShareButtons();
    });

    observer.observe(document.body, {
        childList: true,
        subtree: true
    });
})();