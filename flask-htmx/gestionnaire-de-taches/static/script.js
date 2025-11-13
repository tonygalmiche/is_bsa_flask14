// Variables globales
let draggedTask = null;
let resizeMode = null;
let resizeStartX = 0;
let resizeOriginalWidth = 0;
let selectedTask = null;
let tooltipTimeout = null;
let recentlyResizedTasks = new Set(); // Protection contre l'écrasement après redimensionnement

// Initialisation
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOM chargé, initialisation...');
    setupEventListeners();
    setupScrollSync();
    setupDragAndDrop();
    
    // Initialiser le double-clic sur les tâches
    console.log('Initialisation du double-clic sur les tâches...');
    setupTaskDoubleClick();
});

function setupScrollSync() {
    const horizontalScrollbar = document.querySelector('.horizontal-scrollbar');
    const timeSlotContainers = document.querySelectorAll('.time-slots-container');
    const timeHeaderSlotsInner = document.querySelector('.time-header-slots-inner');
    
    if (!horizontalScrollbar || timeSlotContainers.length === 0) {
        return;
    }
    
    let isScrolling = false;
    let lastScrollLeft = horizontalScrollbar.scrollLeft;
    
    // Synchroniser le défilement de la barre horizontale avec tous les containers de slots
    horizontalScrollbar.addEventListener('scroll', function() {
        if (isScrolling) return;
        
        // Protection contre les changements minimes qui pourraient être causés par les mises à jour de tâches
        const scrollLeft = this.scrollLeft;
        if (Math.abs(scrollLeft - lastScrollLeft) < 1) return;
        
        isScrolling = true;
        lastScrollLeft = scrollLeft;
        
        // Synchroniser avec tous les containers de slots
        timeSlotContainers.forEach(container => {
            container.scrollLeft = scrollLeft;
        });
        
        // Synchroniser avec l'en-tête (scroll visuel sans scrollbar)
        if (timeHeaderSlotsInner) {
            timeHeaderSlotsInner.style.transform = `translateX(-${scrollLeft}px)`;
        }
        
        setTimeout(() => { isScrolling = false; }, 10);
    });
    
    // Synchroniser le défilement des containers de slots avec la barre horizontale
    timeSlotContainers.forEach(container => {
        container.addEventListener('scroll', function() {
            if (isScrolling) return;
            isScrolling = true;
            
            const scrollLeft = this.scrollLeft;
            horizontalScrollbar.scrollLeft = scrollLeft;
            
            // Synchroniser avec l'en-tête
            if (timeHeaderSlotsInner) {
                timeHeaderSlotsInner.style.transform = `translateX(-${scrollLeft}px)`;
            }
            
            // Synchroniser avec les autres containers
            timeSlotContainers.forEach(otherContainer => {
                if (otherContainer !== this) {
                    otherContainer.scrollLeft = scrollLeft;
                }
            });
            
            setTimeout(() => { isScrolling = false; }, 10);
        });
    });
}

function setupDragAndDrop() {
    // Ajouter les événements de drag aux slots
    document.querySelectorAll('.time-slot').forEach(slot => {
        slot.addEventListener('dragover', handleDragOver);
        slot.addEventListener('dragenter', handleDragEnter);
        slot.addEventListener('dragleave', handleDragLeave);
        slot.addEventListener('drop', handleDrop);
    });
    
    document.querySelectorAll('.task').forEach(task => {
        task.addEventListener('dragend', function() {
            this.classList.remove('dragging');
            this.style.opacity = '';
            // Retirer la classe du body pour indiquer que le drag est terminé
            document.body.classList.remove('dragging-active');
            draggedTask = null;
        });
    });
}

function setupEventListeners() {
    // Gestion du focus/sélection des tâches
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.task')) {
            // Désélectionner toutes les tâches si on clique ailleurs
            document.querySelectorAll('.task').forEach(task => {
                task.classList.remove('selected');
            });
            selectedTask = null;
        }
    });
}

// Gestion du drag & drop
function handleDragStart(e) {
    draggedTask = e.target;
    e.target.classList.add('dragging');
    
    // Ajouter une classe sur le body pour indiquer qu'un drag est en cours
    document.body.classList.add('dragging-active');
    
    // Stocker les données de la tâche
    e.dataTransfer.setData('text/plain', JSON.stringify({
        taskId: e.target.dataset.taskId,
        operatorId: e.target.dataset.operatorId,
        startSlot: e.target.dataset.startSlot,
        duration: e.target.dataset.duration
    }));
    
    e.dataTransfer.effectAllowed = 'move';
    
    // Feedback visuel
    setTimeout(() => {
        if (draggedTask) {
            draggedTask.style.opacity = '0.5';
        }
    }, 0);
}

function handleDragOver(e) {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    
    // Toujours permettre le drop, même sur un slot occupé
    const timeSlot = e.target.closest('.time-slot');
    if (timeSlot) {
        timeSlot.classList.add('drag-over');
    }
}

function handleDragEnter(e) {
    e.preventDefault();
    // Toujours permettre l'entrée sur n'importe quel slot
    const timeSlot = e.target.closest('.time-slot');
    if (timeSlot) {
        timeSlot.classList.add('drag-over');
    }
}

function handleDragLeave(e) {
    const timeSlot = e.target.closest('.time-slot');
    if (timeSlot && !timeSlot.contains(e.relatedTarget)) {
        timeSlot.classList.remove('drag-over');
    }
}

function handleDrop(e) {
    e.preventDefault();
    
    const timeSlot = e.target.closest('.time-slot');
    if (!timeSlot || !draggedTask) return;
    
    // Nettoyer les classes de feedback visuel
    document.querySelectorAll('.time-slot').forEach(slot => {
        slot.classList.remove('drag-over');
    });
    
    const newOperatorId = parseInt(timeSlot.dataset.operatorId);
    const newStartSlot = parseInt(timeSlot.dataset.slot);
    const taskId = draggedTask.dataset.taskId;
    
    // Envoyer la requête de déplacement
    moveTask(taskId, newOperatorId, newStartSlot);
    
    // Nettoyer
    if (draggedTask) {
        draggedTask.classList.remove('dragging');
        draggedTask.style.opacity = '';
        draggedTask = null;
    }
    
    // Retirer la classe du body pour indiquer que le drag est terminé
    document.body.classList.remove('dragging-active');
}

// Gestion du redimensionnement
function startResize(e, direction) {
    e.preventDefault();
    e.stopPropagation();
    
    const task = e.target.closest('.task');
    if (!task) return;
    
    const slotWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--slot-width'));
    const currentStartSlot = parseInt(task.dataset.startSlot);
    const currentDuration = parseInt(task.dataset.duration);
     
    resizeMode = direction;
    resizeStartX = e.clientX;
    
    // Calculer la largeur originale basée sur les données de la tâche
    resizeOriginalWidth = currentDuration * slotWidth;
    
    
    // S'assurer que les styles CSS sont cohérents avant de commencer le redimensionnement
    task.style.left = `calc(${currentStartSlot} * var(--slot-width))`;
    task.style.width = `calc(${currentDuration} * var(--slot-width) - 2px)`;
    
    task.classList.add('resizing');
    
    document.addEventListener('mousemove', handleResize);
    document.addEventListener('mouseup', stopResize);
    
    // Empêcher la sélection de texte
    document.body.style.userSelect = 'none';
}

function handleResize(e) {
    if (!resizeMode) return;
    
    const task = document.querySelector('.task.resizing');
    if (!task) return;
    
    const deltaX = e.clientX - resizeStartX;
    const slotWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--slot-width'));
    
    if (resizeMode === 'right') {
        // Redimensionnement vers la droite
        const newWidth = Math.max(slotWidth, resizeOriginalWidth + deltaX);
        const newDuration = Math.max(1, Math.round(newWidth / slotWidth));
        const currentStartSlot = parseInt(task.dataset.startSlot);
        
        // S'assurer que la tâche ne dépasse pas la fin du planning (30 slots)
        const maxDuration = 60 - currentStartSlot; // Augmenté à 60 slots pour correspondre au planning réel
        const finalDuration = Math.min(newDuration, maxDuration);
        
        task.style.width = `calc(${finalDuration} * var(--slot-width) - 2px)`;
        task.dataset.duration = finalDuration;
        
    } else if (resizeMode === 'left') {
        // Redimensionnement vers la gauche DÉSACTIVÉ pour simplifier le code
        return; // Ne rien faire
    }
}

function stopResize(e) {
    if (!resizeMode) return;
    
    const task = document.querySelector('.task.resizing');
    if (task) {
        task.classList.remove('resizing');
        
        // Envoyer la requête de redimensionnement
        const taskId = task.dataset.taskId;
        const newDuration = parseInt(task.dataset.duration);
        const newStartSlot = parseInt(task.dataset.startSlot);
        
        // Vérification avant envoi
        if (newDuration && newDuration > 0) {
            // Protéger cette tâche contre l'écrasement pendant 2 secondes
            recentlyResizedTasks.add(taskId);
            setTimeout(() => {
                recentlyResizedTasks.delete(taskId);
            }, 2000);
            
            // Seul le redimensionnement à droite est supporté maintenant
            resizeTask(taskId, newDuration);
        } else {
            showNotification('Erreur: durée invalide lors du redimensionnement', 'error');
        }
    }
    
    resizeMode = null;
    document.removeEventListener('mousemove', handleResize);
    document.removeEventListener('mouseup', stopResize);
    document.body.style.userSelect = '';
}

// Gestion du clavier
function handleKeyDown(e) {
    const task = e.target;
    if (!task.classList.contains('task')) return;
    
    // S'assurer que cette tâche est bien sélectionnée
    if (selectedTask !== task) {
        // Désélectionner les autres tâches
        document.querySelectorAll('.task').forEach(t => {
            t.classList.remove('selected');
        });
        
        // Sélectionner cette tâche
        task.classList.add('selected');
        selectedTask = task;
    }
    
    const taskId = task.dataset.taskId;
    const duration = parseInt(task.dataset.duration);
    
    switch(e.key) {
        case 'ArrowLeft':
            e.preventDefault();
            keyboardMoveTask(taskId, 'left');
            break;
        case 'ArrowRight':
            e.preventDefault();
            keyboardMoveTask(taskId, 'right');
            break;
        case 'ArrowUp':
            e.preventDefault();
            keyboardMoveTask(taskId, 'up');
            break;
        case 'ArrowDown':
            e.preventDefault();
            keyboardMoveTask(taskId, 'down');
            break;
        case '+':
        case '=':
            e.preventDefault();
            resizeTask(taskId, duration + 1);
            return;
        case '-':
            e.preventDefault();
            if (duration > 1) {
                resizeTask(taskId, duration - 1);
            }
            return;
        case 'Delete':
        case 'Backspace':
            e.preventDefault();
            if (confirm('Êtes-vous sûr de vouloir supprimer cette tâche ?')) {
                // TODO: Implémenter la suppression
            }
            return;
    }
}

// Nouvelle fonction simplifiée pour les déplacements clavier
function keyboardMoveTask(taskId, direction) {
    fetch('/keyboard_move_task', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            task_id: taskId,
            direction: direction
        })
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`Erreur HTTP: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Utiliser refreshPlanning AVEC scroll automatique pour tous les déplacements clavier
            // Le scroll suit la tâche pour qu'elle reste toujours visible
            refreshPlanning(taskId, true);
        } else {
            // Afficher le message d'erreur spécifique du serveur
            const errorMessage = data.error || 'Erreur lors du déplacement de la tâche';
            showNotification(errorMessage, 'error');
        }
    })
    .catch(error => {
        showNotification('Erreur de communication avec le serveur', 'error');
    });
}

// Fonctions HTMX/AJAX
function moveTask(taskId, newOperatorId, newStartSlot) {
    fetch('/move_task', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            task_id: taskId,
            operator_id: newOperatorId,
            start_slot: newStartSlot
        })
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Rafraîchir complètement le planning pour voir toutes les tâches poussées AVEC scroll automatique
            refreshPlanning(taskId, true); // true = avec scroll automatique pour drag & drop
        } else {
            showNotification('Erreur lors du déplacement de la tâche', 'error');
        }
    })
    .catch(error => {
        showNotification('Erreur de communication avec le serveur', 'error');
    });
}

function updateTaskPositionDirectly(taskId, newOperatorId, newStartSlot) {
    const taskElement = document.querySelector(`[data-task-id="${taskId}"]`);
    if (!taskElement) {
        return;
    }
    
    // Mettre à jour les données de la tâche
    const duration = parseInt(taskElement.dataset.duration);
    taskElement.dataset.operatorId = newOperatorId;
    taskElement.dataset.startSlot = newStartSlot;
    
    // Mettre à jour la position visuelle
    taskElement.style.left = `calc(${newStartSlot} * var(--slot-width))`;
    
    // Vérifier si on doit changer d'opérateur
    const currentOperatorRow = taskElement.closest('.operator-row');
    const targetOperatorRow = document.querySelector(`.operator-row[data-operator-id="${newOperatorId}"]`);
    
    if (currentOperatorRow && targetOperatorRow && 
        currentOperatorRow.dataset.operatorId !== newOperatorId.toString()) {
        
        // Déplacer la tâche vers le nouvel opérateur
        const targetContainer = targetOperatorRow.querySelector('.time-slots-container');
        
        if (targetContainer) {
            targetContainer.appendChild(taskElement);
        } 
    }
    
    // Maintenir le focus et la sélection
    taskElement.focus();
    taskElement.classList.add('selected');
    selectedTask = taskElement;
    
    // Pas de scroll automatique pour les déplacements clavier pour éviter le problème de quadrillage
}

// Nouvelle fonction pour faire défiler l'ascenseur horizontal pour suivre une tâche
function scrollToFollowTask(taskElement, startSlot, duration) {
    const horizontalScrollbar = document.querySelector('.horizontal-scrollbar');
    if (!horizontalScrollbar) return;
    
    const slotWidth = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--slot-width'));
    const taskStartPos = startSlot * slotWidth;
    const taskEndPos = (startSlot + duration) * slotWidth;
    
    // Calculer la zone visible actuelle
    const scrollLeft = horizontalScrollbar.scrollLeft;
    const containerWidth = horizontalScrollbar.clientWidth;
    
    // La zone visible commence après la colonne des opérateurs (200px)
    // mais en termes de coordonnées de slots, on doit tenir compte du scroll
    const visibleStartPos = scrollLeft;
    const visibleEndPos = scrollLeft + containerWidth - 200; // -200px pour la colonne fixe
    
    let newScrollLeft = scrollLeft;
    const margin = slotWidth * 2; // Marge plus grande pour anticiper
    
    // Si la tâche commence avant la zone visible, faire défiler vers la gauche
    if (taskStartPos < visibleStartPos + margin) {
        newScrollLeft = Math.max(0, taskStartPos - margin);
    }
    // Si la tâche finit après la zone visible, faire défiler vers la droite
    else if (taskEndPos > visibleEndPos - margin) {
        newScrollLeft = taskEndPos - containerWidth + 200 + margin;
    }
    
    // Défilement immédiat pour éviter que la tâche sorte du cadre
    if (Math.abs(newScrollLeft - scrollLeft) > 5) {
        horizontalScrollbar.scrollLeft = newScrollLeft; // Scroll instantané
    }
}

function updateTaskSizeDirectly(taskId, newDuration) {
    const taskElement = document.querySelector(`[data-task-id="${taskId}"]`);
    if (!taskElement) return;
    
    // Mettre à jour les données et la taille
    const startSlot = parseInt(taskElement.dataset.startSlot);
    taskElement.dataset.duration = newDuration;
    taskElement.style.width = `calc(${newDuration} * var(--slot-width) - 2px)`;
    
    // Maintenir le focus et la sélection
    taskElement.focus();
    taskElement.classList.add('selected');
    selectedTask = taskElement;
    
    // Pas de scroll automatique pour éviter le problème de quadrillage
}

function resizeTask(taskId, newDuration, newStartSlot = null, operatorId = null) {
    const requestBody = {
        task_id: taskId,
        duration: newDuration
    };
    
    // Ajouter les paramètres optionnels (conservé pour compatibilité future)
    if (newStartSlot !== null) {
        requestBody.start_slot = newStartSlot;
    }
    
    if (operatorId !== null) {
        requestBody.operator_id = operatorId;
    }
    
    fetch('/resize_task', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify(requestBody)
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Récupérer les données mises à jour du serveur après redimensionnement réussi
            recentlyResizedTasks.delete(taskId);
            
            // Rafraîchir pour récupérer les données mises à jour AVEC scroll automatique
            setTimeout(() => {
                refreshPlanning(taskId, true); // true = avec scroll automatique pour redimensionnement
            }, 50);
        } else {
            showNotification('Erreur lors du redimensionnement de la tâche', 'error');
            
            // En cas d'erreur, restaurer la taille originale
            const taskElement = document.querySelector(`[data-task-id="${taskId}"]`);
            if (taskElement) {
                const originalDuration = parseInt(taskElement.dataset.duration);
                taskElement.style.width = `calc(${originalDuration} * var(--slot-width) - 2px)`;
            }
        }
    })
    .catch(error => {
        showNotification('Erreur de communication avec le serveur', 'error');
        
        // En cas d'erreur réseau, restaurer la taille originale
        const taskElement = document.querySelector(`[data-task-id="${taskId}"]`);
        if (taskElement) {
            const originalDuration = parseInt(taskElement.dataset.duration);
            taskElement.style.width = `calc(${originalDuration} * var(--slot-width) - 2px)`;
        }
    });
}

function refreshPlanning(taskIdToKeepFocused = null, autoScroll = true) {
    // Au lieu de recharger toute la page, on met à jour les données via AJAX
    fetch('/get_planning_data')
    .then(response => response.json())
    .then(data => {
        updateTaskPositions(data.tasks, data.affairs, taskIdToKeepFocused);
        
        // Restaurer le focus sur la tâche qui était sélectionnée
        if (taskIdToKeepFocused) {
            // Utiliser un délai plus long et une approche plus robuste
            const restoreFocus = () => {
                const taskToFocus = document.querySelector(`[data-task-id="${taskIdToKeepFocused}"]`);
                if (taskToFocus) {
                    // S'assurer que la tâche reste sélectionnée et focalisée
                    if (!taskToFocus.classList.contains('selected')) {
                        // Nettoyer d'abord toutes les sélections
                        document.querySelectorAll('.task').forEach(t => {
                            t.classList.remove('selected');
                        });
                        
                        // Sélectionner et focus sur la bonne tâche
                        taskToFocus.classList.add('selected');
                        selectedTask = taskToFocus;
                    }
                    
                    // Toujours remettre le focus
                    taskToFocus.focus();
                    
                    // Faire défiler pour suivre la tâche après mise à jour SEULEMENT si autoScroll est true
                    if (autoScroll) {
                        const newStartSlot = parseInt(taskToFocus.dataset.startSlot);
                        const newDuration = parseInt(taskToFocus.dataset.duration);
                        scrollToFollowTask(taskToFocus, newStartSlot, newDuration);
                    }
                    
                    return true;
                }
                return false;
            };
            
            // Essayer immédiatement, puis avec des délais plus courts si nécessaire
            if (!restoreFocus()) {
                setTimeout(() => {
                    if (!restoreFocus()) {
                        setTimeout(restoreFocus, 50);
                    }
                }, 20);
            }
        }
    })
    .catch(error => {
        showNotification('Erreur lors du rafraîchissement', 'error');
        // En cas d'erreur, on recharge la page comme fallback
        window.location.reload();
    });
}

function updateTaskPositions(tasks, affairs, targetTaskId = null) {
    // Mettre à jour les positions de toutes les tâches
    tasks.forEach(taskData => {
        const taskElement = document.querySelector(`[data-task-id="${taskData.id}"]`);
        if (taskElement) {
            // Mettre à jour les données
            taskElement.dataset.operatorId = taskData.operator_id;
            taskElement.dataset.startSlot = taskData.start_slot;
            taskElement.dataset.duration = taskData.duration;
            taskElement.dataset.affairId = taskData.affaire_id;
            
            // Ne pas écraser la position/taille si la tâche est en cours de redimensionnement
            // ou a été récemment redimensionnée
            if (!taskElement.classList.contains('resizing') && !recentlyResizedTasks.has(taskData.id)) {
                // Optimisation : ne mettre à jour que si les valeurs ont réellement changé
                const currentLeft = taskElement.style.left;
                const currentWidth = taskElement.style.width;
                const newLeft = `calc(${taskData.start_slot} * var(--slot-width))`;
                const newWidth = `calc(${taskData.duration} * var(--slot-width) - 2px)`;
                
                // Mettre à jour seulement si nécessaire pour éviter les re-layouts inutiles
                if (currentLeft !== newLeft) {
                    taskElement.style.left = newLeft;
                }
                if (currentWidth !== newWidth) {
                    taskElement.style.width = newWidth;
                }
            }
            
            // Vérifier si la tâche a changé d'opérateur
            const currentOperatorRow = taskElement.closest('.operator-row');
            const targetOperatorRow = document.querySelector(`.operator-row[data-operator-id="${taskData.operator_id}"]`);
            
            // Ne déplacer dans le DOM QUE si l'opérateur a réellement changé
            if (currentOperatorRow && targetOperatorRow && 
                currentOperatorRow.dataset.operatorId !== taskData.operator_id.toString()) {
                
                // Vérification supplémentaire : s'assurer que c'est un vrai changement d'opérateur
                const currentOperatorId = parseInt(currentOperatorRow.dataset.operatorId);
                const targetOperatorId = taskData.operator_id;
                
                if (currentOperatorId !== targetOperatorId) {
                    // Déplacer la tâche vers le bon opérateur SEULEMENT si nécessaire
                    const targetContainer = targetOperatorRow.querySelector('.time-slots-container');
                    if (targetContainer && !targetContainer.contains(taskElement)) {
                        targetContainer.appendChild(taskElement);
                    }
                }
            }
        }
    });
}

// Notifications
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    
    notification.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        padding: 15px 20px;
        border-radius: 5px;
        color: white;
        font-weight: 500;
        z-index: 1000;
        animation: slideInRight 0.3s ease-out;
    `;
    
    switch(type) {
        case 'error':
            notification.style.backgroundColor = '#dc3545';
            break;
        case 'success':
            notification.style.backgroundColor = '#28a745';
            break;
        default:
            notification.style.backgroundColor = '#007bff';
    }
    
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.style.animation = 'slideOutRight 0.3s ease-in';
        setTimeout(() => {
            if (notification.parentNode) {
                notification.parentNode.removeChild(notification);
            }
        }, 300);
    }, 3000);
}

// Styles d'animation pour les notifications
const style = document.createElement('style');
style.textContent = `
    @keyframes slideInRight {
        from {
            transform: translateX(100%);
            opacity: 0;
        }
        to {
            transform: translateX(0);
            opacity: 1;
        }
    }
    
    @keyframes slideOutRight {
        from {
            transform: translateX(0);
            opacity: 1;
        }
        to {
            transform: translateX(100%);
            opacity: 0;
        }
    }
`;
document.head.appendChild(style);

// Utilitaires
function getSlotWidth() {
    return parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--slot-width'));
}

function snapToSlot(position) {
    const slotWidth = getSlotWidth();
    return Math.round(position / slotWidth) * slotWidth;
}

// Gestion du focus et de l'accessibilité
document.addEventListener('click', function(e) {
    if (e.target.classList.contains('task')) {
        // Désélectionner les autres tâches
        document.querySelectorAll('.task').forEach(task => {
            task.classList.remove('selected');
        });
        
        // Sélectionner la tâche cliquée
        e.target.classList.add('selected');
        e.target.focus();
        selectedTask = e.target;
    }
});

// Support tactile pour mobile
let touchStartX = 0;
let touchStartY = 0;
let isTouchDrag = false;

document.addEventListener('touchstart', function(e) {
    if (e.target.closest('.task')) {
        touchStartX = e.touches[0].clientX;
        touchStartY = e.touches[0].clientY;
        isTouchDrag = false;
    }
});

document.addEventListener('touchmove', function(e) {
    if (e.target.closest('.task')) {
        const deltaX = Math.abs(e.touches[0].clientX - touchStartX);
        const deltaY = Math.abs(e.touches[0].clientY - touchStartY);
        
        if (deltaX > 10 || deltaY > 10) {
            isTouchDrag = true;
        }
    }
});

document.addEventListener('touchend', function(e) {
    if (e.target.closest('.task') && isTouchDrag) {
        // Implémenter le déplacement tactile si nécessaire
    }
    isTouchDrag = false;
});

// Fonctions pour les infobulles
function showTooltip(event) {
        const task = event.target.closest('.task');
        if (!task) return;
        
        // Annuler le timeout précédent si il existe
        if (tooltipTimeout) {
            clearTimeout(tooltipTimeout);
        }
        
        // Délai avant affichage de l'infobulle
        tooltipTimeout = setTimeout(() => {
            const tooltip = document.getElementById('task-tooltip');
            const title = task.dataset.title;
            const affairName = task.dataset.affairName;
            const operationName = task.dataset.operationName; // <-- ajouté
            const productQty = task.dataset.productQty ? Math.round(parseFloat(task.dataset.productQty)) : null; // <-- arrondi à un entier
            const derniereDataPrevue = task.dataset.derniereDataPrevue; // <-- ajouté
            const employeIdsTxt = task.dataset.employeIdsTxt; // <-- ajouté
            const composantsNonDisponibles = task.dataset.composantsNonDisponibles; // <-- NOUVEAU
            const duration = task.dataset.duration;
            const startSlot = task.dataset.startSlot;
            const taskId = task.dataset.taskId;
            
            // Calculer la position du slot (date/heure)
            const slotInfo = getSlotInfo(parseInt(startSlot));
            const endSlotInfo = getSlotInfo(parseInt(startSlot) + parseInt(duration) - 1);
            
            // Générer l'URL Odoo pour l'affichage dans l'info-bulle
            let odooUrlHtml = '';
            if (taskId && window.taskOdooConfig && window.taskOdooConfig.urlTemplate) {
                const decodedTemplate = decodeHtmlEntities(window.taskOdooConfig.urlTemplate);
                const taskUrl = decodedTemplate.replace('{}', taskId);
                odooUrlHtml = `<div><strong>URL Odoo:</strong> <small style="word-break: break-all;">${taskUrl}</small></div>`;
            }
            
            // Remplir le contenu de l'infobulle
            const titleElement = tooltip.querySelector('.task-tooltip-title');
            const detailElement = tooltip.querySelector('.task-tooltip-detail');
            
            titleElement.textContent = title;

            //    ${operationName ? `<div><strong>Opération:</strong> ${operationName}</div>` : ''}

            detailElement.innerHTML = `
                ${productQty ? `<div><strong>Reste à produire:</strong> ${productQty}${derniereDataPrevue ? ` - ${derniereDataPrevue}` : ''}</div>` : ''}
                ${employeIdsTxt ? `<div><strong>Opérateurs:</strong> ${employeIdsTxt}</div>` : ''}
                ${composantsNonDisponibles ? `<div><strong>Composants non disponibles:</strong> ${composantsNonDisponibles}</div>` : ''}
                ${affairName ? `<div><strong>Affaire:</strong> ${affairName}</div>` : ''}
                <div><strong>Durée:</strong> ${duration} créneaux</div>
                <div><strong>Période:</strong> ${slotInfo.date} ${slotInfo.period}${duration > 1 ? ' → ' + endSlotInfo.date + ' ' + endSlotInfo.period : ''}</div>
            `;        // Positionner l'infobulle
        const taskRect = task.getBoundingClientRect();
        const tooltipRect = tooltip.getBoundingClientRect();
        
        // Position au-dessus de la tâche, centrée horizontalement
        tooltip.style.left = (taskRect.left + taskRect.width / 2) + 'px';
        tooltip.style.top = (taskRect.top - tooltipRect.height - 10) + 'px';
        
        // Afficher l'infobulle
        tooltip.classList.add('show');
    }, 500); // Délai de 500ms avant affichage
}

function hideTooltip(event) {
    // Annuler l'affichage si la souris sort avant le délai
    if (tooltipTimeout) {
        clearTimeout(tooltipTimeout);
        tooltipTimeout = null;
    }
    
    // Cacher l'infobulle
    const tooltip = document.getElementById('task-tooltip');
    tooltip.classList.remove('show');
}

function getSlotInfo(slotIndex) {
    // Recalculer les informations du slot comme dans le template
    const dayOffset = Math.floor(slotIndex / 2);
    const isMorning = slotIndex % 2 === 0;
    
    const startDate = new Date();
    startDate.setHours(8, 0, 0, 0);
    const currentDate = new Date(startDate.getTime() + (dayOffset * 24 * 60 * 60 * 1000));
    
    const dateStr = currentDate.toLocaleDateString('fr-FR', { day: '2-digit', month: '2-digit' });
    const period = isMorning ? 'AM' : 'PM';
    
    return {
        date: dateStr,
        period: period,
        dayName: currentDate.toLocaleDateString('fr-FR', { weekday: 'short' })
    };
}

// === GESTION DU RECHARGEMENT DES AFFAIRES ===

function setupAffairsReload() {
    const reloadDataBtn = document.getElementById('reload-data-btn');
    
    if (reloadDataBtn) {
        reloadDataBtn.addEventListener('click', reloadAllData);
    }
}

async function reloadAllData() {
    const btn = document.getElementById('reload-data-btn');
    const status = document.getElementById('status-text');
    
    if (!btn || !status) return;
    
    // Désactiver le bouton et changer le texte
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '⏳ Rechargement des données...';
    btn.classList.add('loading');
    
    try {
        const response = await fetch('/api/reload-data', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Succès
            status.textContent = result.message;
            status.className = 'status-text status-success';
            
            // Réactualiser la page après un court délai pour voir les changements
            setTimeout(() => {
                location.reload();
            }, 1000);
            
        } else {
            // Erreur
            status.textContent = result.message;
            status.className = 'status-text status-error';
        }
        
    } catch (error) {
        status.textContent = 'Erreur de connexion';
        status.className = 'status-text status-error';
    }
    
    // Réactiver le bouton
    setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = originalText;
        btn.classList.remove('loading');
        
        // Remettre le statut normal après 3 secondes si pas d'erreur
        if (!status.classList.contains('status-error')) {
            status.className = 'status-text';
        }
    }, 2000);
}

async function reloadAffairs() {
    await reloadData('/api/reload-affairs', 'reload-affairs-btn', 'affaires');
}

async function reloadOperators() {
    await reloadData('/api/reload-operators', 'reload-operators-btn', 'opérateurs');
}

async function reloadData(endpoint, btnId, dataType) {
    const btn = document.getElementById(btnId);
    const status = document.getElementById('status-text');
    
    if (!btn || !status) return;
    
    // Désactiver le bouton et changer le texte
    const originalText = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `⏳ Rechargement des ${dataType}...`;
    btn.classList.add('loading');
    
    try {
        const response = await fetch(endpoint, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        const result = await response.json();
        
        if (result.success) {
            // Succès
            status.textContent = result.message;
            status.className = 'status-text status-success';
            
            // Réactualiser la page après un court délai pour voir les changements
            setTimeout(() => {
                location.reload();
            }, 1000);
            
        } else {
            // Erreur
            status.textContent = result.message;
            status.className = 'status-text status-error';
        }
        
    } catch (error) {
        status.textContent = 'Erreur de connexion';
        status.className = 'status-text status-error';
    }
    
    // Réactiver le bouton
    setTimeout(() => {
        btn.disabled = false;
        btn.innerHTML = originalText;
        btn.classList.remove('loading');
        
        // Remettre le statut normal après 3 secondes si pas d'erreur
        if (!status.classList.contains('status-error')) {
            status.className = 'status-text';
        }
    }, 2000);
}

// Modifier la fonction setupEventListeners pour inclure le rechargement des affaires
const originalSetupEventListeners = setupEventListeners;
setupEventListeners = function() {
    originalSetupEventListeners();
    setupAffairsReload();
};

// Gestion du double-clic pour ouvrir les tâches dans Odoo
function setupTaskDoubleClick() {
    console.log('setupTaskDoubleClick appelée');
    const urlTacheOdoo = window.taskOdooConfig ? window.taskOdooConfig.urlTemplate : '';
    console.log('URL template:', urlTacheOdoo);
    
    if (urlTacheOdoo) {
        const tasks = document.querySelectorAll('.task');
        console.log('Nombre de tâches trouvées:', tasks.length);
        
        // Ajouter un gestionnaire de double-clic sur toutes les tâches
        tasks.forEach(function(taskElement) {
            // Supprimer les anciens gestionnaires pour éviter les doublons
            taskElement.removeEventListener('dblclick', handleTaskDoubleClick);
            
            // Ajouter le nouveau gestionnaire
            taskElement.addEventListener('dblclick', handleTaskDoubleClick);
            
            // Ajouter un curseur pointeur pour indiquer qu'on peut cliquer
            taskElement.style.cursor = 'pointer';
            taskElement.title = 'Double-cliquez pour ouvrir dans Odoo';
        });
        
        console.log('Gestionnaires de double-clic ajoutés à', tasks.length, 'tâches');
    } else {
        console.log('Pas d\'URL template configurée');
    }
}

// Fonction utilitaire pour décoder les entités HTML
function decodeHtmlEntities(str) {
    const textarea = document.createElement('textarea');
    textarea.innerHTML = str;
    return textarea.value;
}

// Gestionnaire de double-clic
function handleTaskDoubleClick(event) {
    console.log('Double-clic détecté sur tâche');
    event.preventDefault();
    event.stopPropagation();
    
    const taskId = this.getAttribute('data-task-id');
    console.log('ID de la tâche:', taskId);
    
    if (taskId && window.taskOdooConfig && window.taskOdooConfig.urlTemplate) {
        // Décoder les entités HTML et remplacer {} par l'ID de la tâche dans l'URL
        const decodedTemplate = decodeHtmlEntities(window.taskOdooConfig.urlTemplate);
        const taskUrl = decodedTemplate.replace('{}', taskId);
        console.log('URL template (brut):', window.taskOdooConfig.urlTemplate);
        console.log('URL template (décodé):', decodedTemplate);
        console.log('URL générée:', taskUrl);
        console.log('Tentative d\'ouverture de l\'URL dans un nouvel onglet...');
        
        // Ouvrir dans un nouvel onglet
        try {
            window.open(taskUrl, '_blank');
            console.log('Commande window.open() exécutée avec succès');
        } catch (error) {
            console.error('Erreur lors de l\'ouverture de l\'URL:', error);
        }
    } else {
        console.log('Données manquantes pour ouvrir la tâche:');
        console.log('- taskId:', taskId);
        console.log('- window.taskOdooConfig:', window.taskOdooConfig);
        console.log('- urlTemplate:', window.taskOdooConfig ? window.taskOdooConfig.urlTemplate : 'undefined');
    }
}
