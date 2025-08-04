// Función para manejar el envío de comentarios
function submitComment() {
    const name = document.getElementById('comment-name').value;
    const rating = document.getElementById('comment-rating').value;
    const comment = document.getElementById('comment-text').value;

    if (!name || !comment) {
        alert('Por favor, complete todos los campos requeridos');
        return;
    }

    // Crear nuevo comentario
    const newComment = {
        name: name,
        rating: rating,
        comment: comment,
        date: new Date().toLocaleDateString()
    };

    // Obtener comentarios existentes
    let comments = JSON.parse(localStorage.getItem('comments')) || [];
    
    // Agregar nuevo comentario
    comments.push(newComment);
    
    // Guardar comentarios actualizados
    localStorage.setItem('comments', JSON.stringify(comments));
    
    // Limpiar formulario
    document.getElementById('comment-form').reset();
    
    // Actualizar la visualización de comentarios
    displayComments();
    
    alert('¡Gracias por tu comentario!');
}

// Función para mostrar los comentarios
function displayComments() {
    const commentsContainer = document.getElementById('comments-container');
    const comments = JSON.parse(localStorage.getItem('comments')) || [];
    
    // Ordenar comentarios por fecha (más recientes primero)
    comments.sort((a, b) => new Date(b.date) - new Date(a.date));
    
    // Crear HTML para los comentarios
    const commentsHTML = comments.map(comment => `
        <div class="testimonial-item">
            <div class="rating mb-3">
                ${Array(parseInt(comment.rating)).fill('<i class="bi bi-star-fill"></i>').join('')}
            </div>
            <p>"${comment.comment}"</p>
            <div class="client-info d-flex align-items-center mt-4">
                <div>
                    <h6 class="mb-0">${comment.name}</h6>
                    <span>${comment.date}</span>
                </div>
            </div>
        </div>
    `).join('');
    
    commentsContainer.innerHTML = commentsHTML;
}

// Inicializar la visualización de comentarios cuando se carga la página
document.addEventListener('DOMContentLoaded', displayComments);
